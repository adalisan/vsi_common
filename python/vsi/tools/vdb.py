import sys
import pdb
import IPython.core.debugger
from bdb import BdbQuit
import os
import signal
from functools import partial

if os.name == 'nt':
  from vsi.windows.named_pipes import Pipe
  import threading
  import ctypes
  ATTACH_SIGNAL = signal.SIGINT
else:
  ATTACH_SIGNAL=signal.SIGUSR1


class Tracer(IPython.core.debugger.Tracer):
  ''' Used by Vdb '''
  def __init__(self, colors=None, skipInput = True, *args, **kwargs):
    try:
      super(Tracer, self).__init__(colors)
    except ValueError:
      #This is JUST IN CASE invalid color is specified, should not be relied on
      super(Tracer, self).__init__('Linux') 
    self.debugger = Vdb(skipInput, self.debugger.color_scheme_table.active_scheme_name, *args, **kwargs)
    #This may be dirty, but is less likely to miss features in the future

class Vdb(IPython.core.debugger.Pdb):
  ''' VSI Debugger '''
  def __init__(self, skipInput=True, *args, **kwargs):
    self.__ignore_next_user_return = skipInput;
    IPython.core.debugger.Pdb.__init__(self, *args, **kwargs);
    self.prompt = 'vdb> '

  #Modifications to skip initial user input
  def user_return(self, frame, return_value):
    if self.__ignore_next_user_return:
      self.__ignore_next_user_return = False;
      self.onecmd('c')#continue, effectively ignoring the first input
    else:
      IPython.core.debugger.Pdb.interaction(self, frame, None)
    
  #everything needed from set_trace, minus sys.settrace
  def _pre_settrace(self, frame=None):
    if frame is None:
      frame = sys._getframe().f_back
    f2 = frame

    self.reset()
    while f2:
      f2.f_trace = self.trace_dispatch
      self.botframe = f2
      f2 = f2.f_back
    self.setup(frame, None)

  #Manually call sys.settrace to use out mods
  def _settrace(self):
    sys.settrace(self.trace_dispatch)

delattr(IPython.core.debugger.OldPdb, 'do_r');
delattr(IPython.core.debugger.OldPdb, 'do_q');
try:
  delattr(IPython.core.debugger.Pdb, 'do_q'); #New quit in newer ipython
except:
  pass
#I HATE these! Too powerful and too easy to do by accident

def runpdb(lines, debugger=None):
  ''' Executes a list of vdb command

      Arguments:
      lines - list/tuple/etc... of strings to be executed as if you were 
              already in the debugger. Useful for setting breakpoints 
              programatically.
              
      Returns the debugger object, since this can only be executed on the
      debugger object, you can optionally pass it in as the second argument
      if you want to call rubpdb multiple times. If you do not, a new
      debugger object is created, and all the "memory" of the last debugger
      is lost, such as breakpoints, etc...'''
  try:
    lines + ' ' #Is str like
    lines = [lines] #make it a lise
  except:
    pass;

  if not debugger:
    debugger = Tracer().debugger;
    
  debugger._pre_settrace(frame=sys._getframe().f_back);
  
  for line in lines:
    debugger.onecmd(line)
  
  debugger._settrace()
  
  return debugger

def get_colors(colors=None):
  if colors is None:
    from IPython import get_ipython
    ip = get_ipython()
    if ip is None:
      colors='Linux'
    else:
     colors = ip.colors
  return colors

def set_trace(frame=None, colors=None):
  ''' Helper function, like pdb.set_trace

      set colors = "NoColor", "Linux", or "LightBG"  ''' 
  colors=get_colors(colors)
  if not frame:
    frame = sys._getframe().f_back
  Tracer(skipInput=False, colors=colors).debugger.set_trace(frame)

def post_mortem(tb=None, colors=None):
  ''' Helper function, like pdb.post_mortem ''' 
  # handling the default
  if tb is None:
    # sys.exc_info() returns (type, value, traceback) if an exception is
    # being handled, otherwise it returns None
    tb = sys.exc_info()[2]
    if tb is None:
      raise ValueError("A valid traceback must be passed if no "
                       "exception is being handled")
  colors = get_colors(colors)
  tracer = Tracer(skipInput=False, colors=colors)
  tracer.debugger.reset()
  tracer.debugger.interaction(None, tb)

def rpdb_post_mortem(tb=None, pwd='vsi'):
  import rpbd2
  #NO idea how to do this right now...

def rpdb_exception_hook(type, value, tb):
  import rpbd2
  #NO idea what to do here...

def rpdb_set_trace(_rpdb2_pwd='vsi', *args, **kwargs):
  ''' Works, but without the other parts, it's far from auto '''
  import rpdb2
  print 'Starting rpdb2...'
  rpdb2.start_embedded_debugger(_rpdb2_pwd, *args, **kwargs)
  
def set_attach(db_cmd=None):
  ''' Set up this process to be "debugger attachable" 
  
      Just like gdb can attach to a running process, if you execute this on a 
      process, now you can "attach" to the running python using the attach 
      command

      This works pretty well, and allows you to resume the code UNLESS you are
      running in windows and happen to interrupt a sleep command.'''
  #Todo: Add tcp OPTION?

  signal.signal(ATTACH_SIGNAL, partial(handle_db, db_cmd=db_cmd))
  if os.name == 'nt':
    thread = threading.Thread(target=pipe_server)
    thread.daemon = True
    thread.start()
  #print(os.getpid())
  
def attach(pid, rdpb=True):
  ''' Trigger a python pid that's been already run set_attach
  
      This is the second part of attaching to a python process. Once 
      set_attach is run, on another prompt running attach will trigger
      the interrupt thing attaching or triggering whatever db_cmd was'''
  if os.name == 'nt':
    pipe = Pipe('vdb_%d' % pid)
    pipe.write('vsi')
    pipe.close()
  else:
    os.kill(pid, ATTACH_SIGNAL)

def pipe_server():
  ''' Part of attach/set_attach '''
  while 1:
    pipe = Pipe('vdb_%d' % os.getpid(), server=True)
    knock = pipe.read(3)
    if knock == 'vsi':
      os.kill(0, signal.CTRL_C_EVENT)      
      #ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0, os.getpid())
    pipe.disconnect()
    pipe.close()

def handle_db(sig, frame, db_cmd=None):
  ''' signal handler part of attach/set_attach '''
  if sig == ATTACH_SIGNAL:
    #if not hasattr(sys, 'ps1'): #If not interactive
    if db_cmd:
      db_cmd()
    else: #default behavior
      set_trace(frame)

def dbstop_if_error(colors=None):
  ''' Run this to auto start the debugger on an exception. '''
  sys.excepthook = partial(dbstop_exception_hook, colors=colors)

def dbstop_exception_hook(type, value, tb, colors=None):
    if hasattr(sys, 'ps1') or not sys.stderr.isatty():
    # we are in interactive mode or we don't have a tty-like
    # device, so we call the default hook
      sys.__excepthook__(type, value, tb)
    else:
      import traceback, pdb
      #we are NOT in interactive mode, print the exception
      traceback.print_exception(type, value, tb)
      #print
      # ...then start the debugger in post-mortem mode.
      # pdb.pm() # deprecated
      post_mortem(tb, colors=colors) # more "modern"

def main():
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('--pid', '-p', type=int, default=None)
  parser.add_argument('--rpdb', '--rpdb2', '-r', type=bool, default=False, action='store_true')
  parser.add_argument('--password', '--pw', default='vsi')
  #Add * args here
  args = parser.parse_args()
  
  if args.pid:
    #attach to a pid
    if args.rpdb:
      import rpdb2
      #This is going to take some trickery... need --pwd, --attach {pid#} exposed...
    else:
      attach(args.pid)
  else:
    pass #Do whatever pdb does to run the command

if __name__=='__main__':
  main()