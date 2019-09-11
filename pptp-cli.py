#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import threading
import time


class PPTP(object):

    def __init__(self):
        self.CONF_PATH = "/etc/ppp/peers/macpptp"
        self.configure_path()

    def configure_path(self):
        if not os.path.exists("/etc/ppp/peers"):
            os.mkdir("/etc/ppp/peers")
        if not os.path.exists("/etc/ppp/options"):
            os.system("touch /etc/ppp/options")
        if os.path.isfile(self.CONF_PATH):
            print("Old configuration exists, killing pppd")
            os.system("pkill -9 pppd")
            os.unlink(self.CONF_PATH)

    def write_config(self, username, password, endpoint):
        config_content = """
    plugin /System/Library/SystemConfiguration/PPPController.bundle/Contents/PlugIns/PPPDialogs.ppp
    plugin PPTP.ppp
    noauth
    debug
    #logfile /tmp/ppp.log 
    remoteaddress {0}
    redialcount 1
    redialtimer 5
    idle 1800
    #mru 1320
    mtu 1320
    receive-all
    novj 0:0
    ipcp-accept-local
    ipcp-accept-remote
    #noauth
    #refuse-pap
    #refuse-chap-md5
    refuse-eap
    user {1}
    hide-password
    #noaskpassword
    #mppe-stateless 
    #mppe-128 
    mppe-stateful 
    require-mppe 
    passive 
    looplocal 
    password {2} 
    nodetach
    defaultroute
    #replacedefaultroute
    ms-dns 8.8.8.8
    usepeerdns
        """
        config_content = config_content.format(endpoint, username, password)
        config_file = open(self.CONF_PATH, mode="w")
        config_file.write(config_content)
        config_file.flush()
        config_file.close()

    def dial(self):
        print("Connecting ...")
        self.proc = subprocess.Popen(['pppd', 'call', 'macpptp'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.process_thread = threading.Thread(target=self.output_reader)
        self.process_thread.start()
        try:
            while self.proc.poll() is None:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("Quiting ...")
        finally:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=1)
                print('pppd exited with code ', self.proc.returncode)
            except subprocess.TimeoutExpired:
                print('subprocess did not terminate in time')
            self.process_thread.join()

    def output_reader(self):
        for line in iter(self.proc.stdout.readline, b''):
            print('{0}'.format(line.decode('utf-8')), end='')

    def kill(self):
        if self.proc is not None:
            self.proc.terminate()
        if self.process_thread is not None:
            self.process_thread.join()


if __name__ == "__main__":
    if os.getuid() != 0:
        print("Requires root access")
        sys.exit(1)
    parser = argparse.ArgumentParser()
    parser.add_argument('username', help='Username')
    parser.add_argument('password', help='Password')
    parser.add_argument('endpoint', help='Server Endpoint')
    args = parser.parse_args()
    pptp = PPTP()
    pptp.write_config(args.username, args.password, args.endpoint)
    try:
        pptp.dial()
    except KeyboardInterrupt:
        pptp.kill()
