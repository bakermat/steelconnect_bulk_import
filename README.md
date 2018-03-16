# steelconnect_bulk_import
Imports sites, uplinks and zones based on a CSV file.

## Getting Started
USAGE:
    steelconnect_bulk_import.py scm.riverbed.cc organization -f file

example.csv can be used as a template.

### Prerequisites
Designed to work with both Python2 and Python3.

Requires the Requests library to be installed:
- pip install requests
- pip3 install requests

CSV file needs the following headers:
    name,longname,tags,street_address,city,country,
    timezone,zone_name,zone_ip,vlan,internet_ip,internet_gw,
    wan_name,wan_ip,wan_gw

wan_name needs to match existing WAN name in SCM

## Acknowledgments
Based on Greg Mueller's scrap_set_node_location.py:
https://github.com/grelleum/SteelConnect/blob/master/scrap_set_node_location.py