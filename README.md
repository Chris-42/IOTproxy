# IOTproxy for enverbridge logging without need for the portal

inspired by
https://gitlab.eitelwein.net/MEitelwein/Enverbridge-Proxy

decoding Initially taken from thread in FHEM forum:
https://forum.fhem.de/index.php?topic=61867.0

Added code to work with mqtt
fhem is not tested.

packages pydns and paho.mqtt.client are needed

call is enverproxy.py [-c <configfile>]
  default config is /etc/enverproxy.conf

  you can configure fhem and/or mqtt to send the status of your inverters to.
  if the converters are in standby at evening the submission of 'bad' values (like temp -40°) are suppressed.
  the tcp keepalives from everbridge are handled local.
  if there is no contact to envertecportal the measurements are still send to smarthome hub.
  
  setup is done by configuring a local dns entry in your local DNS server like pihole or fritzbox www.envertecportal.com pointing to this proxy server. The server is looking up the real ip of envertecportal at startup (default at 8.8.8.8) and forwarding all data traffic to this server. It's also possible to add a fallback ip if dns lookup fails.

Install:
  copy enverproxy.conf to /etc/ (or adapt enverproxy.service to use -c argument)
  copy the whole directory to i.e. /usr/local/sbin (if you use a different location you have to adapt enverproxy.service)
  copy enverproxy.service to /etc/systemd/system/
  systemctl enable enverproxy.service
  systemctl start enverproxy.service




known part of the protocol:

each packet has some kind of checksum at the end, calculation unknown (yy16)

client commands:

  680030681006 - poll
    # cmd          account  unknown                    (wid2 stat dc   act  totalkWh temp ac   freq            ) crc?
    # ---------------------------------------------------------------------------------------------------------------
    # 680030681006 yyyyyyyy 00000000 0200 0010 0223 00020000 0000 0000 0000 00000000 0000 0000 0000 000000000000 xx16
    # 680030681006 yyyyyyyy 00000000 0200 0010 0223 0002wwww 3021 297c 1a22 pppppppp 238c 3a5f 3200 000000000000 xx16
      on poll after a submission of inverter data the part after byte 22 seems to contain the content of the last measurement packet

  6803d6681004 - inverter data
    
    # cmd          account  ?id?     unknown      inverter0[32] .. inverter29[32] crc?
    # --------------------------------------------------------------------------------
    # 6803d6681004 yyyyyyyy iiiiiiii 000000000000 xxxxxxxx  ...                   xx16
    
      for each inverter:    
      # Information from bytearray of one inverter (length is 32 bytes)
      # 0        4    6    8    10       14   16   18   20                    31  
      # ------------------------------------------------------------------------
      # wrid     stat dc   pwr  totalkWh temp ac   freq remain                    
      # ------------------------------------------------------------------------
      # xxxxxxxx 3021 40d0 352b 111c5f39 1d66 3872 3204 000000000000000000000000
        stat is 3021 if inverter is active, 0021 if some kind of half standby not filled dc, power, temp
        dc /= 512 V
        power /= 64 W
        totalkWh /= 8192 kWh
        temp = / 128 - 40 °C
        ac /= 64 V
        freq /= 256 Hz
        remain sometimes contain unknown data


server commands:

  680012681015 - Server ack for measurement data
    # -------------------------------------------------------------------------------------------
    # cmd          account  ?id?          crc?
    # -------------------------------------------------------------------------------------------
    # 680012681015 yyyyyyyy iiiiiiii 0000 a116
      ?id? is the same as sent in inverter data packet

  680030681007 - on remote brigge command
    # -------------------------------------------------------------------------------------------
    # cmd          account  ?        ?    ?    ?    ?    wrid stat dc   act  totalkWh temp ac   freq ?            crc?
    # -------------------------------------------------------------------------------------------
    # 680030681007 yyyyyyyy 00000000 0200 0010 0223 0002 1870 3021 28b8 1103 00006a6e 1ee6 3a80 3204 000000000000 5816
        # act was seen as 1103 on bridge reboot request from portal?

  680020681027 - server local date + total (accout) kWh
    # -------------------------------------------------------------------------------------------
    # cmd          account  power    date                                        crc?
    # -------------------------------------------------------------------------------------------
    # 680020681027 yyyyyyyy pppppppp HHMMmmdd 0000 0000 0000 0000 0000 0000 0000 xx16
      power is in 10 Wh (/100 to get kWh)

  68001e681070  - Server time (Cn timezone)
    # -------------------------------------------------------------------------------------------
    # cmd          account  ?        ?  date                                crc?
    # -------------------------------------------------------------------------------------------
    # 68001e681070 yyyyyyyy 00000000 7a mmddHHMMSS 0000 0000 0000 0000 0000 xx16
