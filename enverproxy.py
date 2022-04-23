#!/usr/bin/python

import sys
import os
from iotproxy import TCPProxy
from log import log
import configparser
import signal
import DNS
import json
import argparse
try:
    import paho.mqtt.client as mqtt
except:
    mqtt = False
try:
    from FHEM import FHEM
except:
    FHEM = False

class Enverproxy:

    def __init__(self, configfile, logger):
        self._log = log('Enverproxy') if logger is None else logger
        config = configparser.ConfigParser()
        section = 'enverproxy'
        if os.path.isfile(configfile):
            config_keys = [ 'listen_port',
                            'forward_ip']
            #config['internal']['conf_file'] = configfile
            config.read(configfile)
            if section not in config:
                self._log.logMsg(f'Section {section} is missing in config file {configfile}', log.CRITICAL)
                raise ValueError
            for k in config_keys:
                if k not in config[section]:
                    self._log.logMsg(f'required config variable "{k}" is missing in config file {configfile}', log.CRITICAL)
                    raise ValueError
        else:
            self._log.logMsg(f'Configuration file {configfile} not found', log.CRITICAL)
            raise ValueError
        # Process configuration data
        forward_ip = False
        if 'portal' in config[section]:
            portal     = config[section]['portal']
            dns_server = config.get(section, 'dns_server', fallback= '8.8.8.8')
        if portal != '' and dns_server != '':
            retries = 0
            d = DNS.DnsRequest(server=dns_server, timeout=3)
            while forward_ip == False and retries < 3:
                try:
                    r=d.req(name=portal,qtype='A')
                    if len(r.answers) < 1:
                        self._log.logMsg('dns record empty', log.WARN)
                    else:
                        self._log.logMsg(f"got IP {r.answers[0]['data']}", log.DEBUG)
                        forward_ip = r.answers[0]['data']
                        break
                except DNS.Error:
                    self._log.logMsg(f'dns lookup failed ({retries})', log.INFO)
                retries += 1
        if forward_ip == False:
            self._log.logMsg('dns lookup failed, using fallback', log.WARN)
            if not 'forward_ip' in config[section]:
                self._log.logMsg(f'forward_ip not in found in file {configfile}', log.CRITICAL)
                raise ValueError
            forward_ip = config[section]['forward_ip']
        else:
            self._log.logMsg(f'using {forward_ip} for portal access', log.INFO)
        listen_ip   = config.get(section, 'listen_ip', fallback='')
        listen_port = int(config[section]['listen_port'])
        forward_port = int(config.get(section, 'forward_port', fallback= listen_port))
        forward_timeout = int(config.get(section, 'forward_timeout', fallback= 10))
        section = 'log'
        log_level   = config.get(section, 'log_level', fallback= log.WARN)
        self._log_hex = False
        if log_level == '4.5':
            self._log_hex = True
        log_level   = int(float(log_level))
        log_type    = config.get(section, 'log_type', fallback= 'sys.stdout')
        if log_type == 'syslog':
            log_address = config.get(section, 'log_address', fallback= '127.0.0.1')
            log_port    = int(config.get(section, 'log_port', fallback= 514))
            self._log   = log('EnverProxy', log_level, log_type, log_address, log_port)
        else:
            self._log.logMsg(f'set log to {log_type} {log_level}', log.INFO)
            self._log   = log('EnverProxy', log_level, log_type)
        self._iotserver = TCPProxy(listen_ip, listen_port, forward_ip, forward_port, self._log)
        self._iotserver.set_forward_timeout(forward_timeout)
        if 'mqtt' in config:
            section = 'mqtt'
            mqtt_host = config.get(section, 'host', fallback= 'localhost')
            mqtt_port = int(config.get(section, 'port', fallback= 1883))
            self._send_json = config.get(section, 'send_json', fallback= False) == 'True'
            self._log.logMsg(f'Starting mqtt client to {mqtt_host}:{mqtt_port}', log.INFO)
            self._mqtt_client = mqtt.Client()
            self._mqtt_client.connect(mqtt_host, mqtt_port)
            self._mqtt_client.loop_start()
            self._mqtt_topic = config.get(section, 'base_topic', fallback= 'enverproxy')
        self._fhem_url = False
        if 'fhem' in config:
            if not FHEM:
                self._log.logMsg('FHEM module not loaded', log.CRITICAL)
                raise ValueError
            section = 'fhem'
            fhem_host = config.get(section, 'host', fallback= 'localhost')
            protocol = config.get(section, 'protocol', fallback= 'https')
            fhem_port     = int(config.get(section, 'port', fallback= 8083))
            self._log.logMsg('Starting FHEM client', log.INFO)
            self._fhem_url  = f"{protocol}://{fhem_host}:{fhem_port}/fhem?"
            self._user      = config.get(section, 'user', fallback= '')
            self._password  = config.get(section, 'password', fallback= '')
            self._id2device = config.get(section, 'id2device', fallback= 'noconf')
        self._iotserver.register_callback(self.data_cb)

    def publish_data(self, values):
        wrid = values['wrid']
        #mqtt
        if self._mqtt_client:
            self._log.logMsg('sending mqtt', log.DEBUG)
            if not self._mqtt_client.is_connected():
                self._mqtt_client.reconnect()
            if self._mqtt_client.is_connected():
                if self._send_json:
                    json_object = json.dumps(values, indent = None)
                    topic = {self._mqtt_topic}/{wrid}
                    self._log.logMsg(f'send {topic} :{json_object}', log.DEBUG)
                    self._mqtt_client.publish(topic, json_object)
                else:
                    for key, value in values.items():
                        if key == 'wrid':
                            continue
                        topic = f'{self._mqtt_topic}/{wrid}/{key}'
                        self._log.logMsg(f'send {topic} :{value}', log.DEBUG)
                        self._mqtt_client.publish(topic, value)
        # Fhem
        if self._fhem_url:
            self._log.logMsg('sending to fhem', log.DEBUG)
            fhem_server = FHEM(self._fhem_url, self._user, self._password, self._log)
            if wrid in self._id2device:
                #values = ['wrid', 'ac', 'dc', 'temp', 'power', 'totalkwh', 'freq']
                for key, value in values.items():
                    fhem_cmd = f'set {self._id2device[wrid]} {key} {value}'
                    self._log.logMsg(f'fhem command: {fhem_cmd}', log.DEBUG)
                    fhem_server.send_command(fhem_cmd)
            else:
                self._log.logMsg(f'No FHEM device known for converter ID {wrid}', log.WARN)

    
    def process_data(self, data):
        # Extract information from bytearray
        # 0        4    6    8    10       14   16   18   20                       32
        # -------------------------------------------------------------------------------------------
        # wrid     stat dc   pwr  totalkWh temp ac   freq rest                     next
        # -------------------------------------------------------------------------------------------
        # xxxxxxxx 2202 40d0 352b 001c5f39 1d66 3872 3204 0000
        # 12881870 3021 2b64 3707 0000b276 2240 3b1d 31fd 000000000000000000000000 xxx...
        
        pos = 0
        wrid = data[pos:pos+4].hex()
        #while wrid != '00000000':
        while pos < len(data):
            if wrid != '00000000':
                status = data[pos+4:pos+6].hex()
                dc = '{0:.2f}'.format(int.from_bytes(data[pos+6:pos+8],"big") / 512)
                power = '{0:.2f}'.format(int.from_bytes(data[pos+8:pos+10],"big") / 64)
                total = '{0:.2f}'.format(int.from_bytes(data[pos+10:pos+14],"big") / 8192)
                temp = '{0:.2f}'.format(int.from_bytes(data[pos+14:pos+16],"big") / 128 - 40)
                ac = '{0:.2f}'.format(int.from_bytes(data[pos+16:pos+18],"big") / 64)
                freq = '{0:.2f}'.format(int.from_bytes(data[pos+18:pos+20],"big") / 256)
                remaining = data[pos+20:pos+32].hex()
                if status == '3021':
                    result = {'wrid' : wrid, 'status' : status, 'dc' : dc, 'power' : power, 'totalkwh' : total, 'temp' : temp, 'ac' : ac, 'freq' : freq, 'remaining' : remaining}
                else:
                    result = {'wrid' : wrid, 'status' : status, 'ac' : ac, 'freq' : freq, 'remaining' : remaining}
                self._log.logMsg(result, log.INFO)
                self.publish_data(result)
            pos += 32
            wrid = data[pos:pos+4].hex()
 

    def data_cb(self, data_type, data):
        self._log.logMsg(f'callback for {data_type}data ({len(data)})', log.DEBUG)
        if data_type == 'client':
            
            if data[:6].hex() == '680030681006':
                if self._log_hex:
                    self._log.logMsg(f'ClientPoll as hex: {data[10:].hex()}', log.INFO)
            elif data[:6].hex() == '680030681010':
                self._log.logMsg(f'ClientWridAck', log.INFO)
                if self._log_hex:
                    self._log.logMsg(f'ClientAck as hex: {data[10:].hex()}', log.INFO)
            elif data[:6].hex() == '6803d6681004':
                # payload from converter
                if self._log_hex:
                    # count filled inverter blocks
                    p = 2
                    zerocount = 0
                    while int.from_bytes(data[-(p+32):-p], 'big') == 0:
                        zerocount += 1
                        p += 32
                    self._log.logMsg(f'ClientMonData as hex: {data[10:-p].hex()} {zerocount} empty {data[-2:].hex()}', log.INFO)
                self.process_data(data[20:-2])
            else:
                self._log.logMsg(f'Client sent message with unknown content and length {len(data)}', log.WARN)
                self._log.logMsg(f'unknown Clientdata as hex: {data.hex()}', 3)
        else: # server data
            if data[:6].hex() == '680030681007': # on remote brigge command
                # -------------------------------------------------------------------------------------------
                # cmd          account  ?id?     ?    ?    ?    ?    wrid stat dc   cmd  totalkWh temp ac   freq ?            crc?
                # -------------------------------------------------------------------------------------------
                # 680030681007 yyyyyyyy 00000000 0200 0010 0223 0002 1870 3021 28b8 1103 00006a6e 1ee6 3a80 3204 000000000000 5816
                # cmd 1103  -> reboot?
                if self._log_hex:
                    self._log.logMsg(f'Bridgecmd hex: {data[10:].hex()}', log.INFO)
                self._log.logMsg(f'Bridgecmd {data[28:30].hex()}', log.INFO)
            elif data[:6].hex() == '680020681009':
                # -------------------------------------------------------------------------------------------
                # cmd          account  ?        ?            wrid 1   wrid 2   wrid 3   crc?
                # -------------------------------------------------------------------------------------------
                # 680020681009 yyyyyyyy 00000000 000000000000 wwwwwwww wwwwwwww wwwwwwww 0a16
                if self._log_hex:
                    self._log.logMsg(f'ServerSetWrids hex: {data[10:].hex()}', log.INFO)
                self._log.logMsg(f'ServerSetWrids {data[20:-2].hex()}', log.INFO)
            elif data[:6].hex() == '680020681027':
                # -------------------------------------------------------------------------------------------
                # cmd          account  power    date                                        crc?
                # -------------------------------------------------------------------------------------------
                # 680020681027 yyyyyyyy 00000345 HHMMmmdd 0000 0000 0000 0000 0000 0000 0000 xx16
                if self._log_hex:
                    self._log.logMsg(f'Serverdate hex: {data[10:].hex()}', log.INFO)
                power     = int.from_bytes(data[10:14],"big")
                self._log.logMsg(f'Serverdate {data[17]:02d}.{data[16]:02d}. {data[14]:02d}:{data[15]:02d} [{power/100:.2f}kWh] remain {data[18:32].hex()}', log.INFO)
            elif data[:6].hex() == '680012681015':
                # -------------------------------------------------------------------------------------------
                # cmd          account  ?id?          crc?
                # -------------------------------------------------------------------------------------------
                # 680012681015 yyyyyyyy 1402070d 0000 a116
                if self._log_hex:
                    self._log.logMsg(f'Serverack hex: {data[10:].hex()}', log.INFO)
                self._log.logMsg("Server ack " + str(data[10:16].hex()), log.INFO)
            elif data[:6].hex() == '68001e681070':
                # -------------------------------------------------------------------------------------------
                # cmd          account  power    ?  date                                crc?
                # -------------------------------------------------------------------------------------------
                # 68001e681070 yyyyyyyy 00000000 7a mmddHHMMSS 0000 0000 0000 0000 0000 xx16
                if self._log_hex:
                    self._log.logMsg(f'Servertime hex: {data[10:].hex()}', log.INFO)
                self._log.logMsg(f'Servertime(China) {data[16]:02d}.{data[15]:02d}. {data[17]:02d}:{data[18]:02d}:{data[19]:02d} {data[14]:02x}({data[14]}) remain {data[10:14].hex()} {data[20:30].hex()}', log.INFO)
            else:
                self._log.logMsg(f'unknown Serverdata as hex: {data.hex()}', log.WARN)            
        return data

    def run(self):
        self._iotserver.loop()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Enverproxy')
    parser.add_argument('-c', '--config', dest='configfile', type=argparse.FileType('r'), default='/etc/enverproxy.conf', 
                    help='config file for Enverproxy, defaults to /etc/enverproxy.conf')
    args = parser.parse_args()
    logger = log(identifier='Envertec proxy', verbosity = log.INFO, log_type = 'stdout')
    enverproxy = Enverproxy(args.configfile.name, logger)
    if enverproxy: 
        enverproxy.run()

