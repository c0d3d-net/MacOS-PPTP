import sys
import os
import time
import subprocess
from PySide2.QtCore import QThread, Signal, QObject, Slot, QProcess
from PySide2.QtWidgets import QApplication, QDialog, QLineEdit, QPushButton, QVBoxLayout, QTextEdit, QLabel


class IfconfigMonitor(QThread):
    onConnected = Signal()
    stopped = False

    def run(self):
        while not self.stopped:
            process = QProcess()
            process.start("ifconfig")
            process.waitForFinished(1000)
            output = process.readAll()
            output = str(output, 'utf-8')
            print(output)
            if "ppp0" in output or "ppp1" in output:
                self.onConnected.emit()
                print("Connected")
                self.stopped = True
                break
            else:
                self.sleep(1)


class OutputThread(QThread):
    onLogs = Signal(str)

    def __init__(self, process, parent=None):
        QThread.__init__(self, parent)
        self.proc = process

    def run(self):
        for line in iter(self.proc.stdout.readline, b''):
            self.onLogs.emit(line.decode('utf-8'))


class ProcessThread(QThread):
    onFinished = Signal()
    onStarted = Signal()

    def run(self):
        self.process = subprocess.Popen(['pppd', 'call', 'macpptp'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.onStarted.emit()
        try:
            while self.process.poll() is None:
                self.sleep(1)
        finally:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
                print('pppd exited with code ', self.process.returncode)
            except subprocess.TimeoutExpired:
                print('subprocess did not terminate in time')
            self.onFinished.emit()


class PPTP(QObject):
    onStd = Signal(str)
    onConnected = Signal()
    onDisconnected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
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
        self.process_thread = ProcessThread()
        self.process_thread.onFinished.connect(self.onProcessStopped)
        self.process_thread.onStarted.connect(self.onProcessStarted)
        self.process_thread.start()

    def kill(self):
        if self.process_thread.process is not None:
            self.process_thread.process.terminate()
        if self.process_thread is not None:
            self.process_thread.terminate()

        if self.logger_thread is not None:
            self.logger_thread.terminate()

    @Slot()
    def onProcessStarted(self):
        self.logger_thread = OutputThread(self.process_thread.process)
        self.logger_thread.onLogs.connect(self.onLogs)
        self.logger_thread.start()
        self.monitor = IfconfigMonitor()
        self.monitor.onConnected.connect(self.onConnected)
        self.monitor.start()

    @Slot()
    def onProcessStopped(self):
        if self.logger_thread is not None:
            self.logger_thread.terminate()
        if self.monitor is not None:
            self.monitor.stopped = True
            self.monitor.terminate()
        self.onDisconnected.emit()

    @Slot(str)
    def onLogs(self, data):
        self.onStd.emit(data)


class Form(QDialog):

    def __init__(self, parent=None):
        super(Form, self).__init__(parent)
        self.not_connected = True
        self.pptp = PPTP()
        self.pptp.onConnected.connect(self.onConnected)
        self.pptp.onDisconnected.connect(self.onDisconnected)
        self.setWindowTitle("MacOS PPTP Dialer")
        self.lblUsername = QLabel("Username : ")
        self.username = QLineEdit()
        self.lblPassword = QLabel("Password : ")
        self.password = QLineEdit()
        self.lblEndpoint = QLabel("Endpoint : ")
        self.endpoint = QLineEdit()
        self.button = QPushButton("Connect")
        self.logs = QTextEdit()
        layout = QVBoxLayout()

        layout.addWidget(self.lblUsername)
        layout.addWidget(self.username)
        layout.addWidget(self.lblPassword)
        layout.addWidget(self.password)
        layout.addWidget(self.lblEndpoint)
        layout.addWidget(self.endpoint)
        layout.addWidget(self.button)
        layout.addWidget(self.logs)

        self.logs.setReadOnly(True)

        self.setLayout(layout)

        self.button.clicked.connect(self.onButtonClicked)

        self.password.setEchoMode(QLineEdit.Password)

    def onButtonClicked(self):
        if self.not_connected:
            self.pptp.write_config(self.username.text(), self.password.text(), self.endpoint.text())
            self.pptp.dial()
            self.pptp.onStd.connect(self.onLogsRecieved)
            self.button.setText("Disconnect")
            self.not_connected = False
        else:
            self.pptp.kill()
            self.not_connected = True
            self.button.setText("Connect")

    @Slot(str)
    def onLogsRecieved(self, log):
        self.logs.append(log)

    @Slot()
    def onDisconnected(self):
        self.not_connected = True
        self.button.setText("Connect")
        self.logs.append("Disconnected")

    @Slot()
    def onConnected(self):
        self.logs.append("Connected to " + self.endpoint.text())


if __name__ == "__main__":
    app = QApplication(sys.argv)

    form = Form()
    form.show()

    sys.exit(app.exec_())
