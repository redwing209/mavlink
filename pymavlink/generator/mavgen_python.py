#!/usr/bin/env python
'''
parse a MAVLink protocol XML file and generate a python implementation

Copyright Andrew Tridgell 2011
Released under GNU GPL version 3 or later
'''

import sys, textwrap, os
from . import mavparse, mavtemplate

t = mavtemplate.MAVTemplate()

def generate_preamble(outf, msgs, basename, args, xml):
    print("Generating preamble")
    t.write(outf, """
'''
MAVLink protocol implementation (auto-generated by mavgen.py)

Generated from: ${FILELIST}

Note: this file has been auto-generated. DO NOT EDIT
'''

import struct, array, time, json, os, sys, platform

from ...generator.mavcrc import x25crc

WIRE_PROTOCOL_VERSION = "${WIRE_PROTOCOL_VERSION}"
DIALECT = "${DIALECT}"

PROTOCOL_MARKER_V1 = 0xFE

native_supported = platform.system() != 'Windows' # Not yet supported on other dialects
native_force = 'MAVNATIVE_FORCE' in os.environ # Will force use of native code regardless of what client app wants
native_testing = 'MAVNATIVE_TESTING' in os.environ # Will force both native and legacy code to be used and their results compared

if native_supported:
    try:
        import mavnative
    except ImportError:
        print("ERROR LOADING MAVNATIVE - falling back to python implementation")
        native_supported = False

# some base types from mavlink_types.h
MAVLINK_TYPE_CHAR     = 0
MAVLINK_TYPE_UINT8_T  = 1
MAVLINK_TYPE_INT8_T   = 2
MAVLINK_TYPE_UINT16_T = 3
MAVLINK_TYPE_INT16_T  = 4
MAVLINK_TYPE_UINT32_T = 5
MAVLINK_TYPE_INT32_T  = 6
MAVLINK_TYPE_UINT64_T = 7
MAVLINK_TYPE_INT64_T  = 8
MAVLINK_TYPE_FLOAT    = 9
MAVLINK_TYPE_DOUBLE   = 10


class MAVLink_header(object):
    '''MAVLink message header'''
    def __init__(self, dialect, msgId, incompat_flags=0, compat_flags=0, mlen=0, seq=0, srcSystem=0, srcComponent=0):
        self.mlen = mlen
        self.seq = seq
        self.srcSystem = srcSystem
        self.srcComponent = srcComponent
        self.dialect = dialect
        self.msgId = msgId
        self.incompat_flags = incompat_flags
        self.compat_flags = compat_flags

    def pack(self):
        if WIRE_PROTOCOL_VERSION == '2.0':
            return struct.pack('<BBBBBBBBH', ${PROTOCOL_MARKER}, self.mlen,
                               self.incompat_flags, self.compat_flags,
                               self.seq, self.srcSystem, self.srcComponent,
                               self.dialect, self.msgId)
        return struct.pack('<BBBBBB', PROTOCOL_MARKER_V1, self.mlen, self.seq,
                           self.srcSystem, self.srcComponent, self.msgId)

class MAVLink_message(object):
    '''base MAVLink message class'''
    def __init__(self, dialect, msgId, name):
        self._header     = MAVLink_header(dialect, msgId)
        self._payload    = None
        self._msgbuf     = None
        self._crc        = None
        self._fieldnames = []
        self._type       = name

    def get_msgbuf(self):
        if isinstance(self._msgbuf, bytearray):
            return self._msgbuf
        return bytearray(self._msgbuf)

    def get_header(self):
        return self._header

    def get_payload(self):
        return self._payload

    def get_crc(self):
        return self._crc

    def get_fieldnames(self):
        return self._fieldnames

    def get_type(self):
        return self._type

    def get_msgId(self):
        return self._header.msgId

    def get_srcSystem(self):
        return self._header.srcSystem

    def get_srcComponent(self):
        return self._header.srcComponent

    def get_seq(self):
        return self._header.seq

    def __str__(self):
        ret = '%s {' % self._type
        for a in self._fieldnames:
            v = getattr(self, a)
            ret += '%s : %s, ' % (a, v)
        ret = ret[0:-2] + '}'
        return ret

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        if other == None:
            return False

        if self.get_type() != other.get_type():
            return False

        # We do not compare CRC because native code doesn't provide it
        #if self.get_crc() != other.get_crc():
        #    return False

        if self.get_seq() != other.get_seq():
            return False

        if self.get_srcSystem() != other.get_srcSystem():
            return False            

        if self.get_srcComponent() != other.get_srcComponent():
            return False   
            
        for a in self._fieldnames:
            if getattr(self, a) != getattr(other, a):
                return False

        return True

    def to_dict(self):
        d = dict({})
        d['mavpackettype'] = self._type
        for a in self._fieldnames:
          d[a] = getattr(self, a)
        return d

    def to_json(self):
        return json.dumps(self.to_dict())

    def pack(self, mav, crc_extra, payload):
        self._payload = payload
        self._header  = MAVLink_header(self._header.dialect, self._header.msgId, mlen=len(payload), seq=mav.seq,
                                       srcSystem=mav.srcSystem, srcComponent=mav.srcComponent)
        self._msgbuf = self._header.pack() + payload
        crc = x25crc(self._msgbuf[1:])
        if ${crc_extra}: # using CRC extra
            crc.accumulate_str(struct.pack('B', crc_extra))
        self._crc = crc.crc
        self._msgbuf += struct.pack('<H', self._crc)
        return self._msgbuf

""", {'FILELIST' : ",".join(args),
      'PROTOCOL_MARKER' : xml.protocol_marker,
      'DIALECT' : os.path.splitext(os.path.basename(basename))[0],
      'crc_extra' : xml.crc_extra,
      'WIRE_PROTOCOL_VERSION' : xml.wire_protocol_version })

def generate_enums(outf, enums):
    print("Generating enums")
    outf.write('''
# enums

class EnumEntry(object):
    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.param = {}
        
enums = {}
''')    
    wrapper = textwrap.TextWrapper(initial_indent="", subsequent_indent="                        # ")
    for e in enums:
        outf.write("\n# %s\n" % e.name)
        outf.write("enums['%s'] = {}\n" % e.name)
        for entry in e.entry:
            outf.write("%s = %u # %s\n" % (entry.name, entry.value, wrapper.fill(entry.description)))
            outf.write("enums['%s'][%d] = EnumEntry('%s', '''%s''')\n" % (e.name,
                                                                          int(entry.value), entry.name,
                                                                          entry.description))
            for param in entry.param:
                outf.write("enums['%s'][%d].param[%d] = '''%s'''\n" % (e.name,
                                                                       int(entry.value),
                                                                       int(param.index),
                                                                       param.description))

def generate_message_ids(outf, msgs):
    print("Generating message IDs")
    outf.write("\n# message IDs\n")
    outf.write("MAVLINK_MSG_ID_BAD_DATA = -1\n")
    for m in msgs:
        outf.write("MAVLINK_MSG_DIALECT_%s = %u\n" % (m.name.upper(), m.dialect))
        outf.write("MAVLINK_MSG_ID_%s = %u\n" % (m.name.upper(), m.id))

def generate_classes(outf, msgs):
    print("Generating class definitions")
    wrapper = textwrap.TextWrapper(initial_indent="        ", subsequent_indent="        ")
    for m in msgs:
        classname = "MAVLink_%s_message" % m.name.lower()
        fieldname_str = ", ".join(map(lambda s: "'%s'" % s, m.fieldnames))
        ordered_fieldname_str = ", ".join(map(lambda s: "'%s'" % s, m.ordered_fieldnames))

        outf.write("""
class %s(MAVLink_message):
        '''
%s
        '''
        dialect = MAVLINK_MSG_DIALECT_%s
        id = MAVLINK_MSG_ID_%s
        name = '%s'
        fieldnames = [%s]
        ordered_fieldnames = [ %s ]
        format = '%s'
        native_format = bytearray('%s', 'ascii')
        orders = %s
        lengths = %s
        array_lengths = %s
        crc_extra = %s

        def __init__(self""" % (classname, wrapper.fill(m.description.strip()), 
            m.name.upper(), 
            m.name.upper(), 
            m.name.upper(),
            fieldname_str,
            ordered_fieldname_str,
            m.fmtstr,
            m.native_fmtstr,
            m.order_map,
            m.len_map,
            m.array_len_map,
            m.crc_extra))
        if len(m.fields) != 0:
                outf.write(", " + ", ".join(m.fieldnames))
        outf.write("):\n")
        outf.write("                MAVLink_message.__init__(self, %s.dialect, %s.id, %s.name)\n" % (classname, classname, classname))
        outf.write("                self._fieldnames = %s.fieldnames\n" % (classname))
        for f in m.fields:
                outf.write("                self.%s = %s\n" % (f.name, f.name))
        outf.write("""
        def pack(self, mav):
                return MAVLink_message.pack(self, mav, %u, struct.pack('%s'""" % (m.crc_extra, m.fmtstr))
        for field in m.ordered_fields:
                if (field.type != "char" and field.array_length > 1):
                        for i in range(field.array_length):
                                outf.write(", self.{0:s}[{1:d}]".format(field.name,i))
                else:
                        outf.write(", self.{0:s}".format(field.name))
        outf.write("))\n")


def native_mavfmt(field):
    '''work out the struct format for a type (in a form expected by mavnative)'''
    map = {
        'float'    : 'f',
        'double'   : 'd',
        'char'     : 'c',
        'int8_t'   : 'b',
        'uint8_t'  : 'B',
        'uint8_t_mavlink_version'  : 'v',
        'int16_t'  : 'h',
        'uint16_t' : 'H',
        'int32_t'  : 'i',
        'uint32_t' : 'I',
        'int64_t'  : 'q',
        'uint64_t' : 'Q',
        }
    return map[field.type]

def mavfmt(field):
    '''work out the struct format for a type'''
    map = {
        'float'    : 'f',
        'double'   : 'd',
        'char'     : 'c',
        'int8_t'   : 'b',
        'uint8_t'  : 'B',
        'uint8_t_mavlink_version'  : 'B',
        'int16_t'  : 'h',
        'uint16_t' : 'H',
        'int32_t'  : 'i',
        'uint32_t' : 'I',
        'int64_t'  : 'q',
        'uint64_t' : 'Q',
        }

    if field.array_length:
        if field.type == 'char':
            return str(field.array_length)+'s'
        return str(field.array_length)+map[field.type]
    return map[field.type]

def generate_mavlink_class(outf, msgs, xml):
    print("Generating MAVLink class")

    outf.write("\n\nmavlink_map = {\n");
    for m in msgs:
        if m.id < 256:
            outf.write("        MAVLINK_MSG_ID_%s : MAVLink_%s_message,\n" % (
                m.name.upper(), m.name.lower()))
    for m in msgs:
        outf.write("        (MAVLINK_MSG_DIALECT_%s,MAVLINK_MSG_ID_%s) : MAVLink_%s_message,\n" % (
            m.name.upper(), m.name.upper(), m.name.lower()))
    outf.write("}\n\n")

    t.write(outf, """
class MAVError(Exception):
        '''MAVLink error class'''
        def __init__(self, msg):
            Exception.__init__(self, msg)
            self.message = msg

class MAVString(str):
        '''NUL terminated string'''
        def __init__(self, s):
                str.__init__(self)
        def __str__(self):
            i = self.find(chr(0))
            if i == -1:
                return self[:]
            return self[0:i]

class MAVLink_bad_data(MAVLink_message):
        '''
        a piece of bad data in a mavlink stream
        '''
        def __init__(self, data, reason):
                MAVLink_message.__init__(self, MAVLINK_MSG_ID_BAD_DATA, 'BAD_DATA')
                self._fieldnames = ['data', 'reason']
                self.data = data
                self.reason = reason
                self._msgbuf = data

        def __str__(self):
            '''Override the __str__ function from MAVLink_messages because non-printable characters are common in to be the reason for this message to exist.'''
            return '%s {%s, data:%s}' % (self._type, self.reason, [('%x' % ord(i) if isinstance(i, str) else '%x' % i) for i in self.data])

class MAVLink(object):
        '''MAVLink protocol handling class'''
        def __init__(self, file, srcSystem=0, srcComponent=0, use_native=False):
                self.seq = 0
                self.file = file
                self.srcSystem = srcSystem
                self.srcComponent = srcComponent
                self.callback = None
                self.callback_args = None
                self.callback_kwargs = None
                self.send_callback = None
                self.send_callback_args = None
                self.send_callback_kwargs = None
                self.buf = bytearray()
                self.buf_index = 0      # index into self.buf to avoid rewriting the buffer
                self.expected_length = 8
                self.have_prefix_error = False
                self.robust_parsing = False
                self.protocol_marker = ${protocol_marker}
                self.little_endian = ${little_endian}
                self.crc_extra = ${crc_extra}
                self.sort_fields = ${sort_fields}
                self.total_packets_sent = 0
                self.total_bytes_sent = 0
                self.total_packets_received = 0
                self.total_bytes_received = 0
                self.total_receive_errors = 0
                self.startup_time = time.time()
                if native_supported and (use_native or native_testing or native_force):
                    print("NOTE: mavnative is currently beta-test code")
                    self.native = mavnative.NativeConnection(MAVLink_message, mavlink_map)
                else:
                    self.native = None
                if native_testing:
                    self.test_buf = bytearray()

        def set_callback(self, callback, *args, **kwargs):
            self.callback = callback
            self.callback_args = args
            self.callback_kwargs = kwargs

        def set_send_callback(self, callback, *args, **kwargs):
            self.send_callback = callback
            self.send_callback_args = args
            self.send_callback_kwargs = kwargs

        def send(self, mavmsg):
                '''send a MAVLink message'''
                buf = mavmsg.pack(self)
                self.file.write(buf)
                self.seq = (self.seq + 1) % 256
                self.total_packets_sent += 1
                self.total_bytes_sent += len(buf)
                if self.send_callback:
                    self.send_callback(mavmsg, *self.send_callback_args, **self.send_callback_kwargs)

        def buf_len(self):
            return len(self.buf) - self.buf_index

        def bytes_needed(self):
            '''return number of bytes needed for next parsing stage'''
            if self.native:
                ret = self.native.expected_length - self.buf_len()
            else:
                ret = self.expected_length - self.buf_len()
            
            if ret <= 0:
                return 1
            return ret

        def __parse_char_native(self, c):
            '''this method exists only to see in profiling results'''
            m = self.native.parse_chars(c)
            return m

        def __callbacks(self, msg):
            '''this method exists only to make profiling results easier to read'''
            if self.callback:
                self.callback(msg, *self.callback_args, **self.callback_kwargs)

        def parse_char(self, c):
            '''input some data bytes, possibly returning a new message'''
            self.buf.extend(c)

            self.total_bytes_received += len(c)

            if self.native:
                if native_testing:
                    self.test_buf.extend(c)
                    m = self.__parse_char_native(self.test_buf)
                    m2 = self.__parse_char_legacy()
                    if m2 != m:
                        print("Native: %s\\nLegacy: %s\\n" % (m, m2))
                        raise Exception('Native vs. Legacy mismatch')
                else:
                    m = self.__parse_char_native(self.buf)
            else:
                m = self.__parse_char_legacy()

            if m != None:
                self.total_packets_received += 1
                self.__callbacks(m)
            else:
                # XXX The idea here is if we've read something and there's nothing left in
                # the buffer, reset it to 0 which frees the memory
                if self.buf_len() == 0 and self.buf_index != 0:
                    self.buf = bytearray()
                    self.buf_index = 0

            return m

        def __parse_char_legacy(self):
            '''input some data bytes, possibly returning a new message (uses no native code)'''
            if self.buf_len() >= 1 and self.buf[self.buf_index] != ${protocol_marker}:
                magic = self.buf[self.buf_index]
                self.buf_index += 1
                if self.robust_parsing:
                    m = MAVLink_bad_data(chr(magic), "Bad prefix")
                    self.expected_length = 8
                    self.total_receive_errors += 1
                    return m
                if self.have_prefix_error:
                    return None
                self.have_prefix_error = True
                self.total_receive_errors += 1
                raise MAVError("invalid MAVLink prefix '%s'" % magic)
            self.have_prefix_error = False
            if self.buf_len() >= 2:
                if sys.version_info[0] < 3:
                    (magic, self.expected_length) = struct.unpack('BB', str(self.buf[self.buf_index:self.buf_index+2])) # bytearrays are not supported in py 2.7.3
                else:
                    (magic, self.expected_length) = struct.unpack('BB', self.buf[self.buf_index:self.buf_index+2])
                self.expected_length += 8
            if self.expected_length >= 8 and self.buf_len()  >= self.expected_length:
                mbuf = array.array('B', self.buf[self.buf_index:self.expected_length+self.buf_index])
                self.buf_index += self.expected_length
                self.expected_length = 8
                if self.robust_parsing:
                    try:
                        m = self.decode(mbuf)
                    except MAVError as reason:
                        m = MAVLink_bad_data(mbuf, reason.message)
                        self.total_receive_errors += 1
                else:
                    m = self.decode(mbuf)
                return m
            return None

        def parse_buffer(self, s):
            '''input some data bytes, possibly returning a list of new messages'''
            m = self.parse_char(s)
            if m is None:
                return None
            ret = [m]
            while True:
                m = self.parse_char("")
                if m is None:
                    return ret
                ret.append(m)
            return ret

        def decode(self, msgbuf):
                '''decode a buffer as a MAVLink message'''                    
                # decode the header
                if msgbuf[0] != PROTOCOL_MARKER_V1:
                    headerlen = 10
                    try:
                        magic, mlen, incompat_flags, compat_flags, seq, srcSystem, srcComponent, dialect, msgId = struct.unpack('<cBBBBBBBH', msgbuf[:headerlen])
                    except struct.error as emsg:
                        raise MAVError('Unable to unpack MAVLink header: %s' % emsg)
                    mapkey = (dialect,msgId)
                else:
                    headerlen = 6
                    dialect = 0
                    try:
                        magic, mlen, seq, srcSystem, srcComponent, msgId = struct.unpack('<cBBBBB', msgbuf[:headerlen])
                    except struct.error as emsg:
                        raise MAVError('Unable to unpack MAVLink header: %s' % emsg)
                    mapkey = msgId
                if ord(magic) != ${protocol_marker}:
                    raise MAVError("invalid MAVLink prefix '%s'" % magic)
                if mlen != len(msgbuf)-(headerlen+2):
                    raise MAVError('invalid MAVLink message length. Got %u expected %u, msgId=%u headerlen=%u' % (len(msgbuf)-(headerlen+2), mlen, msgId, headerlen))

                if not mapkey in mavlink_map:
                    raise MAVError('unknown MAVLink message ID %s' % str(mapkey))

                # decode the payload
                type = mavlink_map[mapkey]
                fmt = type.format
                order_map = type.orders
                len_map = type.lengths
                crc_extra = type.crc_extra

                # decode the checksum
                try:
                    crc, = struct.unpack('<H', msgbuf[-2:])
                except struct.error as emsg:
                    raise MAVError('Unable to unpack MAVLink CRC: %s' % emsg)
                crcbuf = msgbuf[1:-2]
                if ${crc_extra}: # using CRC extra
                    crcbuf.append(crc_extra)
                crc2 = x25crc(crcbuf)
                if crc != crc2.crc:
                    raise MAVError('invalid MAVLink CRC in msgID %u 0x%04x should be 0x%04x' % (msgId, crc, crc2.crc))

                try:
                    t = struct.unpack(fmt, msgbuf[headerlen:-2])
                except struct.error as emsg:
                    raise MAVError('Unable to unpack MAVLink payload type=%s fmt=%s payloadLength=%u: %s' % (
                        type, fmt, len(msgbuf[6:-2]), emsg))

                tlist = list(t)
                # handle sorted fields
                if ${sort_fields}:
                    t = tlist[:]
                    if sum(len_map) == len(len_map):
                        # message has no arrays in it
                        for i in range(0, len(tlist)):
                            tlist[i] = t[order_map[i]]
                    else:
                        # message has some arrays
                        tlist = []
                        for i in range(0, len(order_map)):
                            order = order_map[i]
                            L = len_map[order]
                            tip = sum(len_map[:order])
                            field = t[tip]
                            if L == 1 or isinstance(field, str):
                                tlist.append(field)
                            else:
                                tlist.append(t[tip:(tip + L)])

                # terminate any strings
                for i in range(0, len(tlist)):
                    if isinstance(tlist[i], str):
                        tlist[i] = str(MAVString(tlist[i]))
                t = tuple(tlist)
                # construct the message object
                try:
                    m = type(*t)
                except Exception as emsg:
                    raise MAVError('Unable to instantiate MAVLink message of type %s : %s' % (type, emsg))
                m._msgbuf = msgbuf
                m._payload = msgbuf[6:-2]
                m._crc = crc
                m._header = MAVLink_header(dialect, msgId, mlen, seq, srcSystem, srcComponent)
                return m
""", xml)

def generate_methods(outf, msgs):
    print("Generating methods")

    def field_descriptions(fields):
        ret = ""
        for f in fields:
            ret += "                %-18s        : %s (%s)\n" % (f.name, f.description.strip(), f.type)
        return ret

    wrapper = textwrap.TextWrapper(initial_indent="", subsequent_indent="                ")

    for m in msgs:
        comment = "%s\n\n%s" % (wrapper.fill(m.description.strip()), field_descriptions(m.fields))

        selffieldnames = 'self, '
        for f in m.fields:
            if f.omit_arg:
                selffieldnames += '%s=%s, ' % (f.name, f.const_value)
            else:
                selffieldnames += '%s, ' % f.name
        selffieldnames = selffieldnames[:-2]

        sub = {'NAMELOWER'      : m.name.lower(),
               'SELFFIELDNAMES' : selffieldnames,
               'COMMENT'        : comment,
               'FIELDNAMES'     : ", ".join(m.fieldnames)}

        t.write(outf, """
        def ${NAMELOWER}_encode(${SELFFIELDNAMES}):
                '''
                ${COMMENT}
                '''
                return MAVLink_${NAMELOWER}_message(${FIELDNAMES})

""", sub)

        t.write(outf, """
        def ${NAMELOWER}_send(${SELFFIELDNAMES}):
                '''
                ${COMMENT}
                '''
                return self.send(self.${NAMELOWER}_encode(${FIELDNAMES}))

""", sub)


def generate(basename, xml):
    '''generate complete python implemenation'''
    if basename.endswith('.py'):
        filename = basename
    else:
        filename = basename + '.py'

    msgs = []
    enums = []
    filelist = []
    for x in xml:
        msgs.extend(x.message)
        enums.extend(x.enum)
        filelist.append(os.path.basename(x.filename))

    for m in msgs:
        if xml[0].little_endian:
            m.fmtstr = '<'
        else:
            m.fmtstr = '>'
        m.native_fmtstr = m.fmtstr
        for f in m.ordered_fields:
            m.fmtstr += mavfmt(f)
            m.native_fmtstr += native_mavfmt(f)
        m.order_map = [ 0 ] * len(m.fieldnames)
        m.len_map = [ 0 ] * len(m.fieldnames)
        m.array_len_map = [ 0 ] * len(m.fieldnames)
        for i in range(0, len(m.fieldnames)):
            m.order_map[i] = m.ordered_fieldnames.index(m.fieldnames[i])
            m.array_len_map[i] = m.ordered_fields[i].array_length
        for i in range(0, len(m.fieldnames)):
            n = m.order_map[i]
            m.len_map[n] = m.fieldlengths[i]

    print("Generating %s" % filename)
    outf = open(filename, "w")
    generate_preamble(outf, msgs, basename, filelist, xml[0])
    generate_enums(outf, enums)
    generate_message_ids(outf, msgs)
    generate_classes(outf, msgs)
    generate_mavlink_class(outf, msgs, xml[0])
    generate_methods(outf, msgs)
    outf.close()
    print("Generated %s OK" % filename)
