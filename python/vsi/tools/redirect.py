import sys
import os
import threading


class Redirect(object):
  ''' A class to easily redirect stdout and stderr to a sting buffer

      There are times in python when using "those kind of libraries" 
      where you have to capture either stdout or stderr, and many 
      situations are tricky. This class will help you, by using a with
      statement.

      with Redirect() as rid:
        some_library.call157()

      print rid.stdout

      There are 4 output pipe of concern, none of which are synced with
      each other (flushed together).

      stdout and stderr from c (referred to as stdout_c, stderr_c) and
      stdout and stderr from python (referred to as stdout_py, stderr_py).

      Most python functions use the python stdout/stderr, controlled by
      sys.stdout and sys.stderr. However c embedded calls are used the 
      c stdout/stderr, usually fd 1 and 2. Because of this, there are 4
      streams to consider
      
      Once Redirect is done, the results are store in
      >>> self.stdout_c - Standard out output for c
      >>> self.stderr_c - Standard error output for c
      >>> self.stdout_py - Standard out output for python
      >>> self.stderr_py - Standard error output for python
      
      When the streams are joint, they both contain the same data.
      In the joint_out and joint_err case, an addtion attribute is defined
      >>> self.stdout - Standard out output
      >>> self.stderr - Standard error output 
      Just to make it easier
      '''
  
  ''' If you want a more complicated scenario, say you want stdout_c and
      stderr_py grouped, and stderr_c and stdout_py groups because you've
      been drinking too much. Well, this is easy to do by calling Redirect
      twice:
      
      with Redirect(stdout_c=None, stderr_py=None) as rid1:
        with Redirect(stderr_c=None, stdout_py=None) as rid2:
          stuff()
          
      Now rid1's buffer has just stderr_c and stdout_py as one joint 
      stream and rid2 has stfout_c and stderr_py as one joing stream'''

  def __init__(self, stdout_c=1, stderr_c=2, 
                     stdout_py=sys.stdout, stderr_py=sys.stderr, 
                     joint=True,
                     joint_outerr=True, joint_out=True, joint_err=True):
    ''' Initialize the Redirect object

        Optional Arguments:
        stdout_c - The fd to be replace, usually 1 will work, but change it 
                   in case this is not right in your case (default: 1)
                   None means to not redirect
        stderr_c - The fd to be replaced, usually 2 will work, but change it 
                   in case this is not right in your case (default: 2)
                   None means to not redirect
        stdout_py - The file object to be replaced (default: sys.stdout)
                    None means to not redirect
        stderr_py - The file object to be replaced (default: sys.stderr)
                    None means to not redirect
        joint - Should ANY of the stream be joined together. This 
                overrides ALL of the following joint options 
        joint_outerr - Should stdout and stderr use the a joint stream or
                       else it will have separate streams (default: True)
        joint_out - Should stdout_c and stdout_py use the a joint stream or
                    else it will have separate streams (default: True)
        joint_err - Should stderr_c and stderr_py use the a joint stream or
                    else it will have separate streams (default: True)'''
    self.stdout_c_fd=stdout_c
    self.stderr_c_fd=stderr_c
    self.stdout_py_fid=stdout_py
    self.stderr_py_fid=stderr_py
    self.joint_outerr=joint_outerr
    self.joint_out=joint_out
    self.joint_err=joint_err

    if not joint:
      self.joint_outerr=False
      self.joint_out=False
      self.joint_err=False

    if self.joint_outerr and (self.joint_out or self.joint_err): #that's an or, not an and
      #Basically if two of the joint are True, All 4 go through one stream
      #I can't see wanting 3 and not the 4th separate.
      self.joint_all = True
    else:
      self.joint_all = False
      
    #Redirect scenarios
    self.std_cs = [] #list of lists of strings for the c outs associates with the pipes
    self.std_pys = [] #list of lists of strings for the python outs associates with the pipes
    
    # This fun piece of code sets up the "Redirect scenarios"
    if self.joint_all:
      #add all together
      self.std_cs.append(['stdout', 'stderr'])
      self.std_pys.append(['stdout', 'stderr'])
    else:
      if self.joint_out:
        #add stdouts together
        self.std_cs.append(['stdout'])
        self.std_pys.append(['stdout'])                         
      else:
        #add stdout_c
        self.std_cs.append(['stdout'])
        self.std_pys.append([])
        #add stdout_py
        self.std_cs.append([])
        self.std_pys.append(['stdout'])                         
      if self.joint_err:
        #add stderrs together
        self.std_cs.append(['stderr'])
        self.std_pys.append(['stderr'])                         
      else:
        #add stderr_c
        self.std_cs.append(['stderr'])
        self.std_pys.append([])
        #add stderr_py
        self.std_cs.append([])
        self.std_pys.append(['stderr'])
        
    self.buffers = [''] * len(self.std_cs)
    
  def __bleed(self, fid, bufferIndex):
    ''' Read all date from fid and store in buffer[bufferIndex]
    
        This function reads large chuncks at a time (for efficientcy and then
        appends them to the appropriate bufffer. When the write pipe is closed,
        the loop will end and then close the read pipe '''

    chunk = True

    while chunk: #while fid isn't closed
      chunk = os.read(fid, 64*1024) #read a chunk
      self.buffers[bufferIndex] += chunk #add to the buffer
    os.close(fid) #Clearn up those fids now
  

  def startMonitor(self, readPipe, bufferIndex):
    ''' Start a read pipe monitoring thread
    
        Runs __bleed in a background thread to capture all the redirected 
        output and stores the information in the self.buffers[bufferIndex].
        
        Appends the thread object to self.tids

        Arguments:
        readPipe - File descriptor number of the read pipe (from by os.pipe)
        bufferIndex - The xth buffer to store the string in. '''
    self.tids.append(threading.Thread(target=self.__bleed, args=(readPipe, bufferIndex)))
    self.tids[-1].start()


  def flush(self):
    ''' Flushes stdout and stderr '''
    sys.stdout.flush()
    sys.stderr.flush()  
  

  def __enter__(self):
    ''' enter function for with statement. 

        Switched out stderr and stdout, and starts pipe threads'''

    #Clear initial arrays
    self.tids = [] #List of threads running __bleed
    self.read_pipes = [] #list of read pipes
    self.write_pipes = [] #list of write pipes
    self.write_fids = [] # list of file objects for the write_pipes

    #Flush
    self.flush()

    #Copy of fds/handles to put back
    if self.stdout_c_fd is not None:
      self.stdout_c_copy = os.dup(self.stdout_c_fd)
    if self.stderr_c_fd is not None:
      self.stderr_c_copy = os.dup(self.stderr_c_fd)
    #self.copied = os.fdopen(os.dup(self.stdout_fd), 'wb') #Copy of stdout handle to put back

    for x in range(len(self.std_cs)):
      #Create the paired pipes
      (r,w) = os.pipe()
      self.read_pipes.append(r)
      self.write_pipes.append(w)
      self.write_fids.append(os.fdopen(w, 'wb'))

      self.startMonitor(r, len(self.read_pipes)-1)

      for std in self.std_cs[x]:
        if getattr(self, std+'_c_fd') is not None: #self.stdxxx_c_fd is not None
          #Replace the c fd with the write pipe
          os.dup2(w, getattr(self, std+'_c_fd'))
      for std in self.std_pys[x]:
        if getattr(self, std+'_py_fid') is not None: #self.stdxxx_py_fid is not None
          setattr(sys, std, self.write_fids[x])

    return self


  def __exit__(self, exc_type=None, exc_value=None, traceback=None):
    ''' exit function for with statement. 

        Restores stdout and sterr, closes write pipe and joins with the 
        threads'''
    #Flush
    self.flush()

    for x in range(len(self.std_cs)):
      self.write_fids[x].close()
      for std in self.std_pys[x]:
        if getattr(self, std+'_py_fid') is not None: #self.stdxxx_py_fid is not None
          #sys.stdxxx = self.stdxxx_py_fid
          setattr(sys, std, getattr(self, std+'_py_fid'))
      for std in self.std_cs[x]:
        if getattr(self, std+'_c_fd') is not None: #self.stdxxx_c_fd is not None
          #Restore stdxxx to original fd
          os.dup2(getattr(self, std+'_c_copy'), #self.stdxxx_c_copy
                  getattr(self, std+'_c_fd'))      #self.stdxxx_c
    # Close the copy now
    if self.stdout_c_fd is not None:
      os.close(self.stdout_c_copy)
    if self.stderr_c_fd is not None:
      os.close(self.stderr_c_copy)

    for tid in self.tids:
      tid.join()
    
    self.__renameBuffer()
      
  def __renameBuffer(self):
    ''' Take the buffers and store them in common names
    
        Instead of accessing self.buffers, the strings are copied to common 
        names, including stdout_c, stderr_c, stdout_py, stdout_py. If 
        joint_out/joint_err is True, then stdout/stderr is defines
        (respectively) just to make it easier'''
    for x in range(len(self.std_cs)):
      for std in self.std_cs[x]:
        setattr(self, std+'_c', self.buffers[x])
      for std in self.std_pys[x]:
        setattr(self, std+'_py', self.buffers[x])
    #Easier names just to make life easier
    if self.joint_out:
      self.stdout = self.stdout_c
    if self.joint_err:
      self.stderr = self.stderr_c
      
if __name__=='__main__':
  with Redirect(joint=False) as rid:
    RedirectTest._RedirectTest__simple()
  print 'Stdout_c:', rid.stdout_c,
  print 'Stderr_c:', rid.stderr_c,
  print 'Stdout_py:', rid.stdout_py,
  print 'Stderr_py:', rid.stderr_py,
  