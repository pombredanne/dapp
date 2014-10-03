import pytest
import six
import yaml

from dapp import protocol_version, DAPPClient, DAPPBadMsgType, DAPPNoSuchCommand, \
    DAPPCommandException


class MyClient(DAPPClient):
    def run(self, ctxt):
        self.call_command('foo', 'bar', ctxt)
        return True, 'success'


class TestClient(object):
    def setup_method(self, method):
        self.lfd = six.BytesIO()
        self.wfd = six.BytesIO()
        self.c = MyClient(listen_fd=self.lfd, write_fd=self.wfd)

        self.some_msg_lines = [b'START', b'ctxt:', b'  foo: bar', b'spam: spam',
            b'dapp_protocol_version: "' + protocol_version.encode('utf8') + b'"',
            b'msg_type: type', b'STOP']
        self.some_msg_dict = {'ctxt': {'foo': 'bar'}, 'spam': 'spam', 'msg_type': 'type',
            'dapp_protocol_version': str(protocol_version)}

        self.call_msg_lines = [b'START', b'ctxt:', b'  spam: spam', b'msg_type: call_command',
            b'dapp_protocol_version: "' + protocol_version.encode('utf8') + b'"',
            b'command_type: foo', b'command_input: bar', b'STOP']
        self.call_msg_dict = {'ctxt': {'spam': 'spam'}, 'msg_type': 'call_command',
            'command_type': 'foo', 'command_input': 'bar',
            'dapp_protocol_version': str(protocol_version)}

        self.no_such_cmd_msg_lines = [b'START', b'ctxt:', b'  foo: bar',
            b'dapp_protocol_version: "' + protocol_version.encode('utf8') + b'"',
            b'msg_type: no_such_command', b'STOP']

        self.cmd_exc_msg_lines = [b'START', b'ctxt:', b'  foo: bar',
            b'dapp_protocol_version: "' + protocol_version.encode('utf8') + b'"',
            b'msg_type: command_exception', b'exception: problem', b'STOP']

        self.cmd_ok_msg_lines =  [b'START', b'ctxt:', b'  spam: spam', b'  foo: bar',
            b'dapp_protocol_version: "' + protocol_version.encode('utf8') + b'"',
            b'msg_type: command_result', b'lres: True', b'res: result', b'STOP']

        self.run_msg_lines = [b'START', b'ctxt:', b'  spam: spam', b'msg_type: run',
            b'dapp_protocol_version: "' + protocol_version.encode('utf8') + b'"', b'STOP']

        self.ok_msg_dict = {'ctxt': {'foo': 'bar', 'spam': 'spam'}, 'msg_type': 'finished',
            'lres': True, 'res': 'success', 'dapp_protocol_version': str(protocol_version)}

    def _read_sent_msg(self, from_pos=0, nbytes=-1):
        where = self.wfd.tell()
        self.wfd.seek(from_pos)
        b = self.wfd.read(nbytes)
        self.wfd.seek(where)
        return b

    def _write_msg(self, msg, seek='where'):
        if isinstance(msg, list):
            msg = b'\n'.join(msg)
        where = self.lfd.tell()
        if not msg.endswith(b'\n'):
            msg = msg + b'\n'
        self.lfd.write(msg)
        if seek == 'where':
            self.lfd.seek(where, 0)
        elif seek == 'start':
            self.lfd.seek(0, 0)
        else:  # end
            self.lfd.seek(0, 2)

    def test_send_msg(self):
        self.c.send_msg('type', ctxt={'foo': 'bar'}, data={'spam': 'spam'})
        msg = self._read_sent_msg()
        assert set(msg.splitlines()) == set(self.some_msg_lines)

    def test_recv_msg(self):
        self._write_msg(self.some_msg_lines)
        msg = self.c.recv_msg()
        assert msg == self.some_msg_dict

    def test_recv_msg_wrong_type(self):
        # we don't test various malformed messages here; they're checked
        #  by test_check_loaded_msg in test_general
        self._write_msg(self.some_msg_lines)
        with pytest.raises(DAPPBadMsgType):
            self.c.recv_msg(allowed_types=['foo'])

    def test_call_command_no_such_command(self):
        self._write_msg(self.no_such_cmd_msg_lines)
        with pytest.raises(DAPPNoSuchCommand):
            self.c.call_command('foo', 'bar', {})

    def test_call_command_command_exception(self):
        self._write_msg(self.cmd_exc_msg_lines)
        with pytest.raises(DAPPCommandException):
            self.c.call_command('foo', 'bar', {})

    def test_call_command_ok(self):
        self._write_msg(self.cmd_ok_msg_lines)
        d = {}
        lres, res = self.c.call_command('foo', 'bar', d)
        assert lres == True
        assert res == 'result'
        assert d == {'spam': 'spam', 'foo': 'bar'}

    def test_pingpong(self):
        # tests a single complex pingpong run on client side
        self._write_msg(self.run_msg_lines, seek='end')
        self._write_msg(self.cmd_ok_msg_lines, seek='start')
        self.c.pingpong()
        
        msgs = self._read_sent_msg().split(b'STOP\nSTART')
        call_msg = msgs[0][len('START\n'):]
        ok_msg = msgs[1][:-len('STOP\n')]
        assert yaml.load(call_msg) == self.call_msg_dict
        assert yaml.load(ok_msg) == self.ok_msg_dict