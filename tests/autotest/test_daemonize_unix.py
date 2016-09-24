'''
LICENSING
-------------------------------------------------

daemoniker: Cross-platform daemonization tools.
    Copyright (C) 2016 Muterra, Inc.
    
    Contributors
    ------------
    Nick Badger
        badg@muterra.io | badg@nickbadger.com | nickbadger.com

    This library is free software; you can redistribute it and/or
    modify it under the terms of the GNU Lesser General Public
    License as published by the Free Software Foundation; either
    version 2.1 of the License, or (at your option) any later version.

    This library is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
    Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public
    License along with this library; if not, write to the
    Free Software Foundation, Inc.,
    51 Franklin Street,
    Fifth Floor,
    Boston, MA  02110-1301 USA

------------------------------------------------------
'''

import unittest
import logging
import tempfile
import os
import time
import shutil
import traceback

from daemoniker._daemonize_unix import Daemonizer
from daemoniker._daemonize_unix import daemonize
from daemoniker._daemonize_unix import _SUPPORTED_PLATFORM
from daemoniker._daemonize_unix import _fratricidal_fork
from daemoniker._daemonize_unix import _filial_usurpation
from daemoniker._daemonize_unix import _autoclose_files

from daemoniker._daemonize_common import _acquire_pidfile


# ###############################################
# "Paragon of adequacy" test fixtures
# ###############################################


# TODO: add signal alarm to avoid infinite hang system calls


import _fixtures


def childproc_daemonizer(pid_file, token, res_path, check_path, check_seed,
                         parent_pid_file):
    try:
        with Daemonizer() as (is_setup, daemonize):
            if is_setup:
                # It should only exist if we run is_setup twice.
                if os.path.exists(check_path):
                    check_seed = 9999
                
                with open(check_path, 'w') as f:
                    f.write(str(check_seed) + '\n')
                    
            is_parent, token, res_path = daemonize(pid_file, token, res_path)
            
            if is_parent:
                with open(parent_pid_file, 'w') as f:
                    f.write(str(os.getpid()) + '\n')
                
            else:
                with open(res_path, 'w') as f:
                    f.write(str(token) + '\n')
                    
            # Wait a moment so that the grandparent can check our PID file
            time.sleep(1)
            
    except:
        logging.error(
            'Failure writing token w/ traceback: \n' +
            ''.join(traceback.format_exc())
        )
        raise


def childproc_daemon(pid_file, token, res_path):
    ''' The test daemon quite simply daemonizes itself, does some stuff
    to confirm its existence, waits for a signal to die, and then dies.
    '''
    # Daemonize ourselves
    daemonize(pid_file)
    
    # Unfortunately we don't have an easy way to deal with logging right now
    # from hypergolix import logutils
    # logname = logutils.autoconfig(suffix='daemon')
    
    # Write the token to the response path
    try:
        with open(res_path, 'w') as f:
            f.write(str(token) + '\n')
            
        # Wait 1 second so that the parent can make sure our PID file exists
        time.sleep(1)
    
    except:
        logging.error(
            'Failure writing token w/ traceback: \n' +
            ''.join(traceback.format_exc())
        )
    
    
def childproc_acquire(fpath):
    ''' Child process for acquiring the pidfile.
    '''
    try:
        pidfile = _acquire_pidfile(fpath)
        
    finally:
        # Wait 1 second so that the parent can make sure our PID file exists
        time.sleep(1)
        # Manually close the pidfile.
        pidfile.close()
        
        
def childproc_fratfork(res_path):
    # Fork again, killing the intermediate.
    _fratricidal_fork()
    
    my_pid = os.getpid()
    with open(res_path, 'w') as f:
        f.write(str(my_pid) + '\n')
        
        
def childproc_fratfork_2(res_path_parent, res_path_child):
    # Fork again, killing the intermediate, but do some work in the middle.
    is_parent = _fratricidal_fork(have_mercy=True)
    
    my_pid = os.getpid()
    
    if is_parent:
        try:
            with open(res_path_parent, 'w') as f:
                f.write(str(my_pid) + '\n')
        finally:
            os._exit(0)
        
    else:
        with open(res_path_child, 'w') as f:
            f.write(str(my_pid) + '\n')
        
        # Force this to last longer than the parent so it doesn't need to wait
        # on us.
        time.sleep(.25)

        
def childproc_filialusurp(umask, chdir, umask_path, sid_path, wdir_path,
                          pid_path):
    _filial_usurpation(chdir, umask)
    # Get our session id
    my_pid = os.getpid()
    sid = os.getsid(my_pid)
    # reset umask and get our set one.
    umask = os.umask(0)
    # Get our working directory.
    wdir = os.path.abspath(os.getcwd())
    
    # Update parent
    # Write the umask to the response path
    with open(umask_path, 'w') as f:
        f.write(str(umask) + '\n')
        
    # Write the sid to the response path
    with open(sid_path, 'w') as f:
        f.write(str(sid) + '\n')
        
    # Write the working dir to the response path
    with open(wdir_path, 'w') as f:
        f.write(wdir + '\n')
        
    # Write the pid to the response path
    with open(pid_path, 'w') as f:
        f.write(str(my_pid) + '\n')


# ###############################################
# Testing
# ###############################################
        
        
@unittest.skipIf(not _SUPPORTED_PLATFORM, 'Unsupported platform.')
class Deamonizing_test(unittest.TestCase):
    def setUp(self):
        ''' Add a check that a test has not called for an exit, keeping
        forks from doing a bunch of nonsense.
        '''
        if _fixtures.__SKIP_ALL_REMAINING__:
            raise unittest.SkipTest('Internal call to skip remaining.')
    
    def test_acquire_file(self):
        ''' Test that locking the pidfile worked. Platform-specific.
        '''
        with tempfile.TemporaryDirectory() as dirname:
            fpath = dirname + '/testpid.txt'
            
            # Multiprocessing ain't workin, yo
            pid = os.fork()
            
            # Parent process
            if pid != 0:
                # Give the child a moment to start up.
                time.sleep(.5)
                
                self.assertTrue(os.path.exists(fpath))
                with self.assertRaises(SystemExit):
                    _acquire_pidfile(fpath, silence_logger=True)
                    
                # Ensure no zombies. See os.waitpid manpage. Immediately return
                # to prevent hanging.
                os.waitpid(-1, os.WNOHANG)
            
            # Child process
            else:
                _fixtures.__SKIP_ALL_REMAINING__ = True
                childproc_acquire(fpath)
                os._exit(0)
        
    def test_filial_usurp(self):
        ''' Test decoupling child from parent environment. Platform-
        specific.
        '''
        umask = 0o027
        chdir = os.path.abspath('/')
        
        with tempfile.TemporaryDirectory() as dirname:
            umask_path = dirname + '/umask.txt'
            sid_path = dirname + '/sid.txt'
            wdir_path = dirname + '/wdir.txt'
            pid_path = dirname + '/pid.txt'
            
            # Multiprocessing ain't workin, yo
            pid = os.fork()
            
            # Parent process
            if pid != 0:
                my_pid = os.getpid()
                my_sid = os.getsid(my_pid)
                
                # Give the child a moment to start up.
                time.sleep(.5)
                
                try:
                    with open(umask_path, 'r') as res:
                        child_umask = int(res.read())
                
                except (IOError, OSError) as exc:
                    raise AssertionError from exc
                
                try:
                    with open(sid_path, 'r') as res:
                        child_sid = int(res.read())
                
                except (IOError, OSError) as exc:
                    raise AssertionError from exc
                
                try:
                    with open(wdir_path, 'r') as res:
                        child_wdir = res.read()
                
                except (IOError, OSError) as exc:
                    raise AssertionError from exc
                
                try:
                    with open(pid_path, 'r') as res:
                        child_pid = int(res.read())
                
                except (IOError, OSError) as exc:
                    raise AssertionError from exc
                    
                self.assertNotEqual(my_sid, child_sid)
                self.assertEqual(child_umask, umask)
                self.assertTrue(child_wdir.startswith(chdir))
                    
                # Ensure no zombies. See os.waitpid manpage.
                os.waitpid(child_pid, os.WNOHANG)
            
            # Child process
            else:
                _fixtures.__SKIP_ALL_REMAINING__ = True
                childproc_filialusurp(
                    umask,
                    chdir,
                    umask_path,
                    sid_path,
                    wdir_path,
                    pid_path
                )
                os._exit(0)
        
    def test_autoclose_fs(self):
        ''' Test auto-closing files. Platform-specific.
        '''
        # We need to shield all of our loggers first!
        logger_fds = []
        for handler in logging.root.handlers:
            if isinstance(handler, logging.StreamHandler):
                logger_fds.append(handler.stream.fileno())
            elif isinstance(handler, logging.SyslogHandler):
                logger_fds.append(handler.socket.fileno())
            elif isinstance(handler, logging.FileHandler):
                logger_fds.append(handler.stream.fileno())
        
        all_fds = []
        num_files = 14
        fs = []
        shielded_fs = []
        shielded_fds = []
        keepers = [0, 7, 13]
        for ii in range(num_files):
            if ii in keepers:
                thisf = tempfile.TemporaryFile()
                shielded_fs.append(thisf)
                shielded_fds.append(thisf.fileno())
                all_fds.append(thisf.fileno())
            else:
                thisf = tempfile.TemporaryFile()
                all_fds.append(thisf.fileno())
                fs.append(thisf)
            
        try:
            _autoclose_files(shielded=shielded_fds + logger_fds)
            
            for f in shielded_fs:
                with self.subTest('Persistent: ' + str(f)):
                    # Make sure all kept files were, in fact, kept
                    self.assertTrue(
                        os.fstat(f.fileno())
                    )
                    
            for f in fs:
                with self.subTest('Removed: ' + str(f)):
                    # Make sure all other files were, in fact, removed
                    with self.assertRaises(OSError):
                        os.fstat(f.fileno())

            # Do it again with no files shielded from closure.
            _autoclose_files(shielded=logger_fds)
            for f in shielded_fs:
                with self.subTest('Cleanup: ' + str(f)):
                    with self.assertRaises(OSError):
                        os.fstat(f.fileno())
        
        # Clean up any unsuccessful tests. Note idempotency of fd.close().
        finally:
            for f in shielded_fs + fs:
                try:
                    fd = f.fileno()
                    f.close()
                    os.close(fd)
                except OSError:
                    pass
        
    def test_frat_fork(self):
        ''' Test "fratricidal" (okay, parricidal) forking (fork and
        parent dies). Platform-specific.
        '''
        with tempfile.TemporaryDirectory() as dirname:
            res_path = dirname + '/response.txt'

            # Multiprocessing has not been working for this.
            inter_pid = os.fork()
            
            # Parent process
            if inter_pid != 0:
                # Give the child a moment to start up.
                time.sleep(.5)
                
                try:
                    with open(res_path, 'r') as res:
                        response = res.read()
                
                except (IOError, OSError) as exc:
                    raise AssertionError from exc
                    
                child_pid = int(response)
                self.assertNotEqual(inter_pid, child_pid)
                
                # Wait to ensure shutdown of other process.
                # Ensure no zombies. See os.waitpid manpage.
                os.waitpid(inter_pid, 0)
                # Wait for the intermediate process to clear (don't os.WNOHANG)
                os.waitpid(-1, 0)
            
                # Make sure the intermediate process is dead.
                with self.assertRaises(OSError):
                    # Send it a signal to check existence (os.kill is badly
                    # named)
                    os.kill(inter_pid, 0)
                
            # Child process
            else:
                _fixtures.__SKIP_ALL_REMAINING__ = True
                childproc_fratfork(res_path)
                os._exit(0)
        
    def test_frat_fork_2(self):
        ''' Test "fratricidal" (okay, parricidal) forking, with mercy
        enabled (so parent doesn't immediately die). Platform-specific.
        '''
        with tempfile.TemporaryDirectory() as dirname:
            res_path_parent = dirname + '/response.txt'
            res_path_child = dirname + '/response_child.txt'

            # Multiprocessing has not been working for this.
            inter_pid = os.fork()
            
            # Parent process
            if inter_pid != 0:
                # Give the child a moment to start up.
                time.sleep(.5)
                
                try:
                    with open(res_path_parent, 'r') as res:
                        response_parent = res.read()
                
                except (IOError, OSError) as exc:
                    raise AssertionError from exc
                
                try:
                    with open(res_path_child, 'r') as res:
                        response_child = res.read()
                
                except (IOError, OSError) as exc:
                    raise AssertionError from exc
                    
                child_pid = int(response_child)
                parent_pid = int(response_parent)
                self.assertNotEqual(inter_pid, child_pid)
                self.assertEqual(inter_pid, parent_pid)
                
                # Wait to ensure shutdown of other process.
                # Ensure no zombies. See os.waitpid manpage.
                os.waitpid(inter_pid, 0)
            
                # Make sure the intermediate process is dead.
                with self.assertRaises(OSError):
                    # Send it a signal to check existence (os.kill is badly
                    # named)
                    os.kill(inter_pid, 0)
                
            # Child process
            else:
                _fixtures.__SKIP_ALL_REMAINING__ = True
                childproc_fratfork_2(res_path_parent, res_path_child)
                os._exit(0)
        
    def test_daemonize(self):
        ''' Test daemonization. Platform-specific.
        '''
        # Manually manage the directory creation and removal so the forks don't
        # destroy it.
        dirname = tempfile.mkdtemp()
            
        pid_file = dirname + '/testpid.pid'
        token = 2718282
        res_path = dirname + '/response.txt'
        
        # Multiprocessing has been failing to test all this, with either
        # "bad value(s) in fds_to_keep" or "bad file descriptors"
        pid = os.fork()
        
        # Parent process
        if pid != 0:
            try:
                # Wait a moment for the daemon to show up
                time.sleep(.5)
                # This is janky, but multiprocessing hasn't been working for
                # events or queues with daemonizing, might have something to
                # do with multiple threads and forking or something
                
                try:
                    with open(res_path, 'r') as res:
                        response = res.read()
                
                except (IOError, OSError) as exc:
                    raise AssertionError from exc
                    
                # Make sure the token matches
                self.assertTrue(response.startswith(str(token)))
                # Make sure the pid file exists
                self.assertTrue(os.path.exists(pid_file))
                    
                # Now hold off just a moment and then make sure the pid is
                # cleaned up successfully. Note that this timing is dependent
                # upon the child process.
                time.sleep(5)
                self.assertFalse(os.path.exists(pid_file))
                    
                # Ensure no zombies. See os.waitpid manpage.
                os.waitpid(pid, os.WNOHANG)
            
            finally:
                # Explicitly call cleanup so that we don't have a competition
                # for removing the temporary directory
                shutil.rmtree(dirname, ignore_errors=True)
            
        # Child process
        else:
            _fixtures.__SKIP_ALL_REMAINING__ = True
            childproc_daemon(pid_file, token, res_path)
            # Hm. So we can't do os._exit, because we need the cleanup to
            # happen to remove the pid file. However, we're deamonized now,
            # so this shouldn't affect the parent.
            raise SystemExit()
                
    def test_context_manager(self):
        ''' Test the context manager. Should produce same results on
        Windows and Unix, but still needs to be run on both.
        '''
        # We need to do this manually because the fork needs to call its own
        # cleanup, and it needs to be before the fork because otherwise the
        # fork won't know its own home
        dirname = tempfile.mkdtemp()
        
        pid_file = dirname + '/testpid.pid'
        token = 2718282
        check_seed = 3179
        res_path = dirname + '/response.txt'
        # Check path is there to ensure that setup code only runs once
        check_path = dirname + '/check.txt'
        parent_pid_file = dirname + '/parentpid.pid'
            
        pid = os.fork()
        
        # Parent process
        if pid != 0:
            try:
                # Wait a moment for the daemon to show up
                time.sleep(.5)
                
                # Now read the res_path if it's available
                try:
                    with open(res_path, 'r') as res:
                        response = res.read()
                
                except (IOError, OSError) as exc:
                    raise AssertionError from exc
                    
                # Make sure the token matches
                try:
                    self.assertEqual(int(response), token)
                except:
                    print(response)
                    raise
                    
                # Make sure the pid file exists
                self.assertTrue(os.path.exists(pid_file))
                
                # Now read the check_path if it's available
                try:
                    with open(check_path, 'r') as f:
                        check = f.read()
                
                except (IOError, OSError) as exc:
                    raise AssertionError from exc
                self.assertEqual(int(check), check_seed)
                
                # Now make sure the parent pid file exists, and that it reads
                # the grandparent pid, and then remove it.
                self.assertTrue(os.path.exists(parent_pid_file))
                with open(parent_pid_file, 'r') as f:
                    grandparent_pid = int(f.read())
                self.assertEqual(grandparent_pid, pid)
                # Don't need to cleanup because it's in a tempdir
                    
                # Now hold off just a moment and then make sure the pid is
                # cleaned up successfully. Note that this timing is dependent
                # upon the child process.
                # Wait for the intermediate process to clear (don't os.WNOHANG)
                os.waitpid(-1, 0)
                time.sleep(2)
                self.assertFalse(os.path.exists(pid_file))
                
                # And verify the check file was not overwritten either
                try:
                    with open(check_path, 'r') as f:
                        check = f.read()
                
                except (IOError, OSError) as exc:
                    raise AssertionError from exc
                self.assertEqual(int(check), check_seed)
            
            finally:
                shutil.rmtree(dirname)
                
        # Child process
        else:
            try:
                childproc_daemonizer(
                    pid_file,
                    token,
                    res_path,
                    check_path,
                    check_seed,
                    parent_pid_file
                )
            
            except:
                with open(res_path,'w') as f:
                    f.write(''.join(traceback.format_exc()))
                print(''.join(traceback.format_exc()))
                raise
            
            finally:
                # Tell unittest that we're done.
                _fixtures.__SKIP_ALL_REMAINING__ = True
                # The thing is, it doesn't really make sense to call this. It's
                # just going to suppress any other errors that get called, and
                # it's caught by unittest regardless. We can't do os._exit,
                # because that prevents cleanup by the daemonized child. So
                # just do nothing beyond skipping all remaining.
                # raise SystemExit()
        

if __name__ == "__main__":
    unittest.main()
