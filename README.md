# IOTproxy for enverbridge logging without need for the portal

inspired by
https://gitlab.eitelwein.net/MEitelwein/Enverbridge-Proxy

decoding Initially taken from thread in FHEM forum:
https://forum.fhem.de/index.php?topic=61867.0

Added code to work with mqtt

call is enverproxy.y [-c <configfile>]
  default config is /etc/enverproxy.conf

  you can configure fhem and/or mqtt to send the status of your inverters to.
  if the converters are in standby at evening the submission of 'bad' values (like temp -40°) are suppressed.
  the tcp keepalives from everbridge are handled local.
  if there is no contact to envertecportal the measurements are still send to smarthome hub.
  
  setup is done by configuring a local dns entry in your local DNS server like pihole or fritzbox www.envertecportal.com pointing to this proxy server. The server is looking up the real ip of envertecportal at startup (default at 8.8.8.8) and forwarding all data traffic to this server. It's also possible to add a fallback ip if dns lookup fails.
  
