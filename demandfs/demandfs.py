#!/usr/bin/env python
 
"""
    demandfs.py - mount and umount sources on demand
    Copyright (C) 2013 Sebastian Meyer <s.meyer@drachenjaeger.eu>
    Based upon the the xmp.py-FS Example in the fuse-python distribtion:
    Copyright (C) 2001 Jeff Epler <jepler@unpythonic.dhs.org>
    Copyright (C) 2006 Csaba Henk <csaba.henk@creo.hu>
    http://sourceforge.net/p/fuse/fuse-python/ci/master/tree/example/xmp.py

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see https://www.gnu.org/licenses/gpl-3.0.
"""

import errno
import fcntl
import subprocess
import sys
import threading
import time
import os

try:
    import fuse
except ImportError as e:
    print "Can't import the python fuse module."
    print "If you use Linux, take a look into your repositories."
    print "Mostly the package is known as python-fuse or fuse-python."
    sys.exit(2)


fuse.fuse_python_api = (0, 2)

TIMER_CHECK_SECONDS = 30  # interval for the timer to check the fs for idle
STATE_LOCK = threading.Lock()  # Lock to protect the mount-state of the fs
BACKDIR = None  # Necessary global for the path to the backdir
VERBOSE = False

def verbose(message):
    """
    Will print message only if VERBOSE is True
    """
    if VERBOSE:
        print message


class Timer(threading.Thread):
    """ 
    Timer will check the idle-state of the Filesystem every 
    TIMER_CHECK_SECONDS seconds
    """

    def __init__(self, dfs):
        """ dfs: the instance of the DemandFileSystem """
        threading.Thread.__init__(self)
        self.dfs = dfs
        self.run_thread = True
        self.timer_event = threading.Event()

    def run(self):
        """ Thread loop to check the idle-state of the Filesystem """
        while self.run_thread:
            verbose("Timer checks for idle...")
            STATE_LOCK.acquire()
            if (dfs.backdir_is_mounted 
                and dfs.last_activity + dfs.timeout < time.time()):
                dfs.umount_backdir()
            STATE_LOCK.release()
            self.timer_event.wait(TIMER_CHECK_SECONDS)
            
            
class DemandFS(fuse.Fuse):
    """
    A Fuse-Layer between a mountpoint (where the FS is mounted) and another
    directory (given as option backdir).
    Every request will reset the timer.y
    """

    def __init__(self, *args, **kw):
        fuse.Fuse.__init__(self, *args, **kw)
        self.backdir = None
        self.timeout = 60
        self.mountscript = None
        self.umountscript = None
        self.backdir_is_mounted = False
        self.last_activity = time.time()
        self.verbose = False
        self.timer = None
        
    def fsinit(self, *args):
        self.timer = Timer(self)
        self.timer.start()
        
    def fsdestroy(self, *args):
        verbose("fsdestroy called with args:" % args)
        self.umount_backdir()
        self.timer.run_thread = False
        self.timer.timer_event.set()
        
    def mount_backdir(self):
        """
        Be sure you have acquired the STATE_LOCK before call this!
        Call the script to mount the backdir. If the script retuns a value
        != 0 we expect the backdir is not available.
        """
        ret = self.run_script(self.mountscript)
        if ret == 0:
            self.backdir_is_mounted = True
            
    def run_script(self, path):
        """ Call this to run an external script """
        try:
            verbose("in try, want to run: %s " % path)
            subprocess.check_output(path, stderr=subprocess.STDOUT)
            #TODO: Log output here
            return 0
        except subprocess.CalledProcessError as e:
            print "External script failed"
            return e.returncode

    def trigger_activity(self):
        """ 
        Called everytime the filesystem is working. It mounts the
        backdir if it is not mounted and renew the last_activity timestamp
        """
        STATE_LOCK.acquire()
        if not self.backdir_is_mounted:
            self.mount_backdir()
        if not self.backdir_is_mounted:
            STATE_LOCK.release()
            return False
        self.last_activity = time.time()
        STATE_LOCK.release()
        return True

    def umount_backdir(self):
        """
        Be sure you have acquired the STATE_LOCK before call this!
        Called the script to mount the backdir. If the script retuns a value
        > 0 we expect the backdir is still available, < 0 the backdir is 
        gone (but not mounted as planned, what is 0)
        """
        if self.backdir_is_mounted:
            ret = self.run_script(self.umountscript)
            if ret == 0:
                self.backdir_is_mounted = False
            else:
                # TODO: Log failure
                print "Can't unmount the backdir"


    # Methods for filesystem-operations:

    def getattr(self, path):
        verbose("gettattr path: %s" % path)
        # don't call the mountscript if it is the root-dir.
        # a "ls" in the parent dir would trigger the mount
        if path == "/":
            return os.lstat(self.backdir + path)
        elif self.trigger_activity():
            return os.lstat(self.backdir + path)
        else:
            return -errno.EIO

    def readlink(self, path):
        verbose("readlink path: %s" % path)
        if self.trigger_activity():
            return os.readlink(self.backdir + path)
        else:
            return -errno.EIO
    
    def readdir(self, path, offset):
        verbose("readdir path offst: %s %s" % (path, offset))
        if not self.trigger_activity():
            yield -errno.EIO
        for e in os.listdir(self.backdir + path):
            yield fuse.Direntry(e)
    

    def unlink(self, path):
        verbose("unlink path: %s" % path)
        if self.trigger_activity():
            os.unlink(self.backdir + path)
        else:
            return -errno.EIO

    def rmdir(self, path):
        verbose("rmdir: %s" % path)
        if self.trigger_activity():
            os.rmdir(self.backdir + path)
        else:
            return -errno.EIO
        
    def symlink(self, path, path1):
        verbose("symlink: %s %s" % (path, path1))
        if self.trigger_activity():
            os.symlink(path, self.backdir + path1)
        else:
            return -errno.EIO

    def rename(self, path, path1):
        verbose("rename path, path1: %s %s" % (path, path1))
        if self.trigger_activity():
            os.rename(self.backdir + path, self.backdir + path1)
        else:
            return -errno.EIO

    def link(self, path, path1):
        verbose("link path, path1): %s %s" % (path, path1))
        if self.trigger_activity():
            os.link(self.backdir + path, self.backdir + path1)
        else:
            return -errno.EIO

    def chmod(self, path, mode):
        verbose("chmod path, mode: %s %s" % (path, mode))
        if self.trigger_activity():
            os.chmod(self.backdir + path, mode)
        else:
            return -errno.EIO

    def chown(self, path, user, group):
        verbose("chown, path, user, group: %s %s %s" % (path, user, group))
        if self.trigger_activity():
            os.chown(self.backdir + path, user, group)
        else:
            return -errno.EIO

    def truncate(self, path, len):
        verbose("truncate: %s %s" % (path, len))
        if self.trigger_activity():
            f = open(self.backdir + path, "a")
            f.truncate(len)
            f.close()
        else:
            return -errno.EIO

    def mknod(self, path, mode, dev):
        verbose("mknot path, mode, dev: %s %s %s" % (path, mode, dev))
        if self.trigger_activity():
            os.mknod(self.backdir + path, mode, dev)
        else:
            return -errno.EIO

    def mkdir(self, path, mode):
        verbose("mkdir path, mode: %s %s" % (path, mode))
        if self.trigger_activity():
            os.mkdir(self.backdir + path, mode)
        else:
            return -errno.EIO

    def utime(self, path, times):
        verbose("utime path, times: %s %s" % (path, times))
        if self.trigger_activity():
            os.utime(self.backdir + path, times)
        else:
            return -errno.EIO
        
    def access(self, path, mode):
        verbose("access path, mode: %s %s" % (path, mode))
        if self.trigger_activity():
            if not os.access(self.backdir + path, mode):
                return -EACCES
        else:
            return -errno.EIO
        
        
    class DemandFile(object):

        def __init__(self, path, flags, *mode):
            self.keep_cache = False
            self.direct_io = False
            path = BACKDIR + path
            verbose("init file with path: %s" % path)
            self.file = os.fdopen(os.open(path, flags, *mode),
                                  self.flag2mode(flags))
            self.fd = self.file.fileno()
            
        def flag2mode(self, flags):
            md = {os.O_RDONLY: 'r', os.O_WRONLY: 'w', os.O_RDWR: 'w+'}
            m = md[flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)]
            if flags | os.O_APPEND:
                m = m.replace('w', 'a', 1)
            return m

        def read(self, length, offset):
            verbose("file read length, offset: %s %s" % (length, offset))
            if self.trigger_activity():
                self.file.seek(offset)
                return self.file.read(length)
            else:
                return -errno.EIO

        def write(self, buf, offset):
            verbose("file write buf, offset: %s %s" % (buf, offset))
            if self.trigger_activity():
                self.file.seek(offset)
                self.file.write(buf)
                return len(buf)
            else:
                return -errno.EIO

        def release(self, flags):
            verbose("file release flags: %s" % flags)
            if self.trigger_activity():
                self.file.close()
            else:
                return -errno.EIO

        def _fflush(self):
            verbose("_fflush!")
            if self.trigger_activity():
                if 'w' in self.file.mode or 'a' in self.file.mode:
                    self.file.flush()
            else:
                return -errno.EIO

        def fsync(self, isfsyncfile):
            verbose("file fsync isfsyncfile %s:" % isfsyncfile)
            if self.trigger_activity():
                self._fflush()
                if isfsyncfile and hasattr(os, 'fdatasync'):
                    os.fdatasync(self.fd)
                else:
                    os.fsync(self.fd)
            else:
                return -errno.EIO

        def flush(self):
            verbose("file flush")
            if self.trigger_activity():
                self._fflush()
                os.close(os.dup(self.fd))
            else:
                return -errno.EIO

        def fgetattr(self):
            verbose("file fgetattr")
            if self.trigger_activity():
                return os.fstat(self.fd)
            else:
                return -errno.EIO

        def ftruncate(self, len):
            verbose("file ftruncate len: %s" % len)
            if self.trigger_activity():
                self.file.truncate(len)
            else:
                return -errno.EIO

        def lock(self, cmd, owner, **kw):
            verbose("file lock cmd, owner: %s %s" % (cmd, owner))
            if self.trigger_activity():
                op = { fcntl.F_UNLCK : fcntl.LOCK_UN,
                       fcntl.F_RDLCK : fcntl.LOCK_SH,
                       fcntl.F_WRLCK : fcntl.LOCK_EX }[kw['l_type']]
                if cmd == fcntl.F_GETLK:
                    return -EOPNOTSUPP
                elif cmd == fcntl.F_SETLK:
                    if op != fcntl.LOCK_UN:
                        op |= fcntl.LOCK_NB
                elif cmd == fcntl.F_SETLKW:
                    pass
                else:
                    return -errno.EINVAL
                fcntl.lockf(self.fd, op, kw['l_start'], kw['l_len'])
            else:
                return -errno.EIO

    def main(self, *a, **kw):
        self.file_class = self.DemandFile
        self.file_class.trigger_activity = self.trigger_activity
        return fuse.Fuse.main(self, *a, **kw)



if __name__ == "__main__":
    dfs = DemandFS()
    dfs.flags = 0
    dfs.multithreaded = 1
    dfs.parser.add_option(mountopt="backdir", metavar="PATH",
                          help="path to the backdir.")
    dfs.parser.add_option(mountopt="timeout", metavar="SEC",
                          help="timeout in sec. before unmount the backdir")
    dfs.parser.add_option(mountopt="mountscript", metavar="PATH",
                          help="path to the script which do the mount")
    dfs.parser.add_option(mountopt="umountscript", metavar="PATH",
                          help="path to the script which do the unmount")
    dfs.parser.add_option(mountopt="verbose", metavar="True/False", 
                          default=False, help="Activate verbose mode")
    dfs.parse(values=dfs, errex=1)
    if isinstance(dfs.verbose, str) and dfs.verbose.lower() == "true":
        dfs.verbose = True
        VERBOSE = True
    dfs.timeout = int(dfs.timeout)
    BACKDIR = dfs.backdir
    dfs.main()