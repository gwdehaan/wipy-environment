#! /usr/bin/env python3
# encoding: utf-8
#
# (C) 2015 Chris Liechti <cliechti@gmx.net>
#
# SPDX-License-Identifier:    BSD-3-Clause
"""\
WiPy helper tool to access file via FTP.
"""
import configparser  # https://docs.python.org/3/library/configparser.html
import ftplib        # https://docs.python.org/3/library/ftplib.html
import glob
import io
import logging
import os
import shutil
import sys
import posixpath
import datetime

INI_TEMPLATE = """\
[FTP]
server = 192.168.1.1
user = micro
pass = python
"""


class WiPySimulator(object):
    def __init__(self, root_directory):
        self.root = os.path.abspath(root_directory)
        self.log = logging.getLogger('FTP')
        self.log.debug('WiPy FTP Simulator in {}'.format(self.root))
        if not os.path.exists(os.path.join(self.root, 'flash')):
            os.mkdir(os.path.join(self.root, 'flash'))
            os.mkdir(os.path.join(self.root, 'flash', 'lib'))

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        pass

    def ls(self, path=None):
        """List files, meant for interactive use"""
        if path is None:
            path = '/'
        print(os.listdir(os.path.join(self.root, path)))

    def walk(self, root):
        yield from os.walk(os.path.join(self.root, posixpath.relpath(root, '/')))

    def makedirs(self, dirname):
        """Recursively create directories, if not yet existing"""
        self.log.info('makedirs {}'.format(dirname))
        os.makedirs(os.path.join(self.root, os.path.relpath(dirname, '/')), exist_ok=True)

    def put(self, filename, fileobj):
        """send binary file"""
        self.log.info('put {}'.format(filename))
        with open(os.path.join(self.root, os.path.relpath(filename, '/')), 'wb') as dst:
            shutil.copyfileobj(fileobj, dst)

    def get(self, filename, fileobj):
        """receive binary file"""
        self.log.info('get {}'.format(filename))
        with open(os.path.join(self.root, os.path.relpath(filename, '/')), 'rb') as src:
            shutil.copyfileobj(src, fileobj)


class WiPyFTP(object):
    def __init__(self, read_ini='wipy-ftp.ini'):
        self.ftp = None
        self.log = logging.getLogger('FTP')
        self.config = configparser.RawConfigParser()
        self.config.read_string(INI_TEMPLATE)
        if read_ini is not None:
            if os.path.exists(read_ini):
                self.config.read(read_ini)
            else:
                logging.warning('"{}" not found, using defaults'.format(read_ini))
        self.log.debug('WiPy IP: {}'.format(self.config['FTP']['server']))
        self.log.debug('FTP user: {}'.format(self.config['FTP']['user']))
        self.log.debug('FTP pass: {}'.format(self.config['FTP']['pass']))

    def __enter__(self):
        self.log.debug('Connecting...')
        self.ftp = ftplib.FTP(self.config['FTP']['server'])
        self.ftp.login(self.config['FTP']['user'], self.config['FTP']['pass'])
        self.log.debug('Connection OK')
        return self

    def __exit__(self, *args, **kwargs):
        self.log.debug('Disconnecting...')
        self.ftp.quit()

    def ls(self, path=None):
        """List files, meant for interactive use"""
        if path is None:
            path = '/'
        try:
            self.ftp.cwd(path)
            self.log.debug('ls {}'.format(self.ftp.pwd()))
            print(self.ftp.retrlines('LIST'))
        except ftplib.error_perm as e:
            self.log.error('invalid path: {} ({})'.format(path, e))
        except ftplib.all_errors as e:
            self.log.error('FTP error: {}'.format(e))

    def walk(self, root):
        """recursively list files on target"""
        self.log.debug('walk {}'.format(root))
        try:
            self.ftp.cwd(root)
            lines = []
            self.ftp.retrlines('LIST', lines.append)
            items = [(x.startswith('d'), x[49:]) for x in lines]
            dirs = [name for is_dir, name in items if is_dir]
            files = [name for is_dir, name in items if not is_dir]
            yield root, dirs, files
            for r in dirs:
                if root == '/':
                    yield from self.walk('/{}'.format(r))
                else:
                    yield from self.walk('{}/{}'.format(root, r))
        except ftplib.error_perm as e:
            self.log.error('invalid path: {} ({})'.format(path, e))
        except ftplib.all_errors as e:
            self.log.error('FTP error: {}'.format(e))


    def makedirs(self, dirname):
        """Recursively create directories, if not yet existing"""
        self.log.info('makedirs {}'.format(dirname))
        try:
            self.ftp.cwd('/')
        except ftplib.error_perm as e:
            self.log.error('invalid path: {} ({})'.format(dirname, e))

        for directory in dirname.split('/')[1:]:
            try:
                self.log.debug('cwd to {}'.format(directory))
                self.ftp.cwd(directory)
            except ftplib.error_perm as e:
                self.log.info('creating directory: {} ({})'.format(dirname, e))
                try:
                    self.ftp.mkd(directory)
                    self.ftp.cwd(directory)
                except ftplib.error_perm as e:
                    self.log.error('error while creating directory: {} ({})'.format(dirname, e))

            except ftplib.all_errors as e:
                self.log.error('FTP error: {}'.format(e))

    def put(self, filename, fileobj):
        """send binary file"""
        try:
            self.log.info('put {}'.format(filename))
            self.ftp.storbinary("STOR " + filename, fileobj, 1024)
        except ftplib.error_perm as e:
            self.log.error('invalid path: {} ({})'.format(filename, e))
        except ftplib.all_errors as e:
            self.log.error('FTP error: {}'.format(e))

    def get(self, filename, fileobj):
        """receive binary file"""
        try:
            self.log.info('get {}'.format(filename))
            self.ftp.retrbinary("RETR " + filename, fileobj.write, 1024)
        except ftplib.error_perm as e:
            self.log.error('invalid path: {} ({})'.format(filename, e))
        except ftplib.all_errors as e:
            self.log.error('FTP error: {}'.format(e))


WLANCONFIG_TEMPLATE = """\
ssid = {ssid!r}
password = {password!r}
"""

ULOG_CONFIG_TEMPLATE = """\
import ulog
ulog.add_remote({ip!r}, {port})
"""

class WiPyActions():

    def __init__(self, target):
        self.target = target

    def __enter__(self):
        self.target.__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        self.target.__exit__()
        pass

    def ls(self, path=None):
        """ lists directory entry """
        self.target.ls(path)

    def put(self, filename, fileobj):
        self.target.put(filename, fileobj)

    def get(self, filename, fileobj):
        self.target.get(filename, fileobj)

    def install_lib(self):
        """recursively copy /flash/lib"""
        base_path = 'device/flash/lib'
        for root, dirs, files in os.walk(base_path):
            if '__pycache__' in dirs:
                dirs.remove('__pycache__')
            self.target.makedirs('/{}'.format(os.path.relpath(root, 'device')))
            for filename in files:
                remote_name = os.path.relpath(os.path.join(root, filename), 'device')
                with open(os.path.join(root, filename), 'rb') as src:
                    remote_name = remote_name.replace('\\', '/')
                    self.target.put('/{}'.format(remote_name), src)

    def install_top(self):
        """copy *.py in /flash"""
        for filename in glob.glob('device/flash/*.py'):
            with open(filename, 'rb') as src:
                self.target.put('/flash/{}'.format(os.path.basename(filename)), src)

    def config_wlan(self):
        ssid = input('Enter SSID: ')
        password = input('Enter passphrase: ')
        self.target.put('/flash/wlanconfig.py',
                        io.BytesIO(WLANCONFIG_TEMPLATE.format(ssid=ssid, password=password).encode('utf-8')))

    def config_ulog(self):
        ip = input('Enter IP: ')
        port = input('UDP port [514]: ')
        if not port:
            port = '514'
        self.target.put('/flash/ulogconfig.py',
                        io.BytesIO(ULOG_CONFIG_TEMPLATE.format(ip=ip, port=int(port)).encode('utf-8')))

    def backup(self):
        """Download all data from /flash"""
        backup_dir = 'backup_{:%Y-%m-%d_%H_%M_%S}'.format(datetime.datetime.now())
        logging.info('backing up /flash into {}'.format(backup_dir))
        for root, dirs, files in self.target.walk('/flash'):
            local_root = os.path.join(backup_dir, posixpath.relpath(root, '/'))
            if not os.path.exists(local_root):
                os.makedirs(local_root)
            for name in files:
                with open(os.path.join(local_root, name), 'wb') as dst:
                    self.target.get(posixpath.join(root, name), dst)


def main():
    import argparse

    parser = argparse.ArgumentParser(
            description='WiPy copy tool',
            epilog="""\
For configuration, a file called ``wipy-ftp.ini`` should be present. Run
"%(prog)s write-ini" to create one. Adapt as needed when connected via
router.
""")

    parser.add_argument('action', type=lambda s: s.lower(), help='Action to execute, try "help"')
    parser.add_argument('path', nargs='?', help='pathname used for some actions')
    parser.add_argument('destination', nargs='?', help='target used for some actions')
    parser.add_argument('-v', '--verbose', action='store_true', help='show more diagnostic messages')
    parser.add_argument('--defaults', action='store_true', help='do not read ini file, use default settings')
    parser.add_argument('--ini', help='alternate name for settings file (default: %(default)s)', default='wipy-ftp.ini')
    parser.add_argument('--simulate', metavar='DIR', help='do not access WiPy, put files in given directory instead')
    # parser.add_argument('--noexp', action='store_true', help='skip steps involving the expansion board and SD storage')

    args = parser.parse_args()
    #~ print(args)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    if args.action == 'write-ini':
        with open(args.ini, 'w') as f:
            f.write(INI_TEMPLATE)
        logging.info('"{}" written'.format(args.ini))
        sys.exit(0)

    if args.simulate:
        logging.info('using simulator')
        target = WiPySimulator(args.simulate)
    else:
        logging.info('using ftp')
        target = WiPyFTP(None if args.defaults else args.ini)

    if args.action == 'cp':
        with WiPyActions(target) as wipy:
            with open(args.path,'rb') as src:
                wipy.put(args.destination, src)
    elif args.action == 'cat':
        with WiPyActions(target) as wipy:
            wipy.get(args.path, sys.stdout.buffer)
    elif args.action == 'ls':
        with WiPyActions(target) as wipy:
            wipy.ls(args.path)
    elif args.action == 'sync-lib':
        with WiPyActions(target) as wipy:
            wipy.install_lib()
    elif args.action == 'sync-top':
        with WiPyActions(target) as wipy:
            wipy.install_top()
    elif args.action == 'install':
        with WiPyActions(target) as wipy:
            wipy.backup()
            wipy.install_top()
            wipy.install_lib()
            if input('Connect to an access point? [Y/n]: ').upper() in ('', 'Y'):
                wipy.config_wlan()
    elif args.action == 'config-wlan':
        with WiPyActions(target) as wipy:
            print('Configure the WiPy to connect to an access point')
            wipy.config_wlan()
    elif args.action == 'config-ulog':
        with WiPyActions(target) as wipy:
            print('Configure the WiPy to send ulog (syslog compatible) messages to following IP address')
            wipy.config_ulog()
    elif args.action == 'fwupgrade':
        with WiPyActions(target) as wipy:
            print('upload /flash/sys/mcuimg.bin')
            wipy.put('/flash/sys/mcuimg.bin', open('mcuimg.bin', 'rb'))
            print('press reset button on WiPy to complete upgrade')
    elif args.action == 'backup':
        with WiPyActions(target) as wipy:
            wipy.backup()
    elif args.action == 'interact':
        # local REPL loop with established FTP connection for development
        with WiPyActions(target) as wipy:
            import code
            try:
                import rlcompleter
                import readline
            except ImportError as e:
                logging.warning('readline support failed: {}'.format(e))
            else:
                readline.set_completer(rlcompleter.Completer(locals()).complete)
                readline.parse_and_bind("tab: complete")
            code.interact(local=locals())
    else:
        sys.stdout.write("""\
ACTIONS are:
- "write-ini" create ``wipy-ftp.ini`` with default settings
- "install"  copy boot.py, main.py and /lib from the PC to the WiPy
- "sync-lib" copies only /lib
- "sync-top" copies only boot.py, main.py
- "config-wlan" ask for SSID/Password and write wlanconfig.py on WiPy
- "ls" with optional remote path argument: list files
- "cp" with local source and remote destination: uploads binary file
- "cat" with remote filename: show file contents
- "backup" download everything in /flash
- "fwupgrade"  write mcuimg.bin file to WiPy for firmware upgrade
- "help"  this text
""")

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
if __name__ == '__main__':
    main()
