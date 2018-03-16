#!/usr/bin/env python3
"""
Imports sites, uplinks and zones based on a CSV file.

Designed to work with both Python2 and Python3.
Requires the Requests library to be installed:
- pip install requests
- pip3 install requests

CSV file needs the following headers:
    name,longname,tags,street_address,city,country,
    timezone,zone_name,zone_ip,vlan,internet_ip,internet_gw,
    wan_name,wan_ip,wan_gw

wan_name needs to match existing WAN name in SCM

USAGE:
    steelconnect_bulk_import.py scm.riverbed.cc organization -f file

Based on Greg Mueller's scrap_set_node_location.py:
https://github.com/grelleum/SteelConnect/blob/master/scrap_set_node_location.py
"""

from __future__ import print_function
import argparse
import collections
import csv
import getpass
import json
import requests
import sys


def main(argv):
    """Interpret CLI, read CSV and show org & site details """
    args = arguments(argv)

    scm, organization = args.cloud_controller, args.organization
    if organization.endswith('.cc') and not scm.endswith('.cc'):
        scm, organization = organization, scm
    baseurl = 'https://' + scm + '/api/scm.config/1.0/'

    file = args.file
    username = args.username if args.username else get_username()
    password = args.password if args.password else get_password(username)
    auth = (username, password)

    sites_csv = open_csv(file)
    org_id = find_org(baseurl, auth, organization)
    # not currently in use for anything, will only show the amount of sites
    sites = find_sites(baseurl, auth, organization, org_id)
    wans = find_wans(baseurl, auth, org_id)

    return add_sites(baseurl, auth, org_id, sites_csv, wans)


def add_sites(baseurl, auth, org_id, sites, wans):
    """Add sites from CSV and add/update uplinks, zones and networks """
    result = []
    for site in sites:
        print('=' * 79 + '\n')
        print('Site: {0}, {1}, {2} ({3})'.format(
            site['name'],
            site['longname'],
            site['city'],
            site['country'])
        )
        print('Zone: {0} ({1})'.format(
            site['zone_name'],
            site['zone_ip'])
        )
        print('Internet uplink IP:\t {0} - gw {1}'.format(
            site['internet_ip'],
            site['internet_gw'] or "dhcp")
        )

        if (site['wan_name']):
            print('{0} uplink IP:\t\t {1} - gw {2}'.format(
                site['wan_name'],
                site['wan_ip'],
                site['wan_gw'] or "dhcp"))
        print('\n')

        payload = json.dumps({
            'org': org_id,
            'city': site['city'],
            'street_address': site['street_address'],
            'timezone': site['timezone'],
            'longname': site['longname'],
            'country': site['country'],
            'name': site['name'],
            'tags': site['tags'],
        })
        url = baseurl + 'org/' + org_id + '/sites'
        response = post(url, payload=payload, auth=auth)
        print('Adding site:\t\t', response.status_code, response.reason)

        if (response.status_code == 200):
            # response.text contains the last added site ID
            result.append(json.loads(response.text))
            site_id = result[-1]['id']

            # Used to attach correct member network to WAN
            update_network_wan_id = None
            zones = find_zones(baseurl, auth, site_id, result)
            internet_uplink_id = find_uplink(baseurl, auth,
                                             site_id, wans.internet)
            if (site['wan_name'] == wans.wan_name):
                add_uplink(baseurl, auth, org_id, site_id,
                           wans.wan_id, site['wan_ip'].lower(), site['wan_gw'])
                update_network_wan_id = wans.wan_id
            if (site['internet_ip'].lower() != "dhcp"):
                update_uplink(baseurl, auth, site_id, wans.internet,
                              site['internet_ip'].lower(),
                              site['internet_gw'], internet_uplink_id)
            update_zones(baseurl, auth, zones, site['zone_name'], site['vlan'])
            update_network(baseurl, auth, zones, site['zone_ip'],
                           wans.routevpn, update_network_wan_id)
    return result


def add_uplink(baseurl, auth, org_id, site_id,
               wan_id, wan_ip, wan_gw):
    """Add uplink to site. """
    payload = prep_payload(site_id, wan_id, wan_ip, wan_gw)
    url = baseurl + 'org/' + org_id + '/uplinks'
    response = post(url, payload=payload, auth=auth)
    print('Adding uplink:\t\t', response.status_code, response.reason)


def update_uplink(baseurl, auth, site_id,
                  wan_id, wan_ip, wan_gw, uplink_id):
    """Update uplink in site. """
    payload = prep_payload(site_id, wan_id, wan_ip, wan_gw)
    url = baseurl + 'uplink/' + uplink_id
    response = put(url, payload=payload, auth=auth)
    print('Updating uplink:\t', response.status_code, response.reason)


def prep_payload(site_id, wan_id, wan_ip, wan_gw):
    """Prepare JSON payload for add/update uplinks. """
    if (wan_ip == 'dhcp'):
        type = 'dhcpd'
        static_ip_v4 = None
        static_gw_v4 = None
    else:
        type = 'static'
        static_ip_v4 = wan_ip
        static_gw_v4 = wan_gw

    payload = json.dumps({
        'site': site_id,
        'wan': wan_id,
        'bgp_learned_routes_ver2': '[]',  # required for API call to go through
        'type': type,
        'static_ip_v4': static_ip_v4,
        'static_gw_v4': static_gw_v4,
    })
    return payload


def update_zones(baseurl, auth, zones, zone_name, zone_vlan):
    """Update zone names and VLANs. """
    payload = json.dumps({
       'name': zone_name,
       'site': zones[0]['site'],
       'tag': zone_vlan,
    })
    url = baseurl + 'zone/' + zones[0]['id']
    response = put(url, payload=payload, auth=auth)
    print('Updating zone:\t\t', response.status_code, response.reason)


def update_network(baseurl, auth,
                   zones, zone_ip, routevpn, wan_id=None):
    """Update network and change subnet to zone_ip. """
    wan_id = [wan_id, routevpn] if wan_id else [routevpn]
    payload = json.dumps({
        # 'Net' seems to be common and is required for the API call.
        'name': 'Net',
        'zone': zones[0]['id'],
        'site': zones[0]['site'],
        'netv4': zone_ip,
        'wans': wan_id,
    })
    url = baseurl + 'network/' + zones[0]['networks'][0]
    response = put(url, payload=payload, auth=auth)
    print('Updating subnet:\t', response.status_code, response.reason)


def find_org(baseurl, auth, organization):
    """Find the org id for the target organization."""
    print('\nFinding organization:')
    orgs = get(baseurl + 'orgs', auth=auth)
    org_found = [org for org in orgs if org['name'] == organization]
    if not org_found:
        org_found = [org for org in orgs if org['longname'] == organization]
    if not org_found:
        print("Could not find and org with name '{0}'".format(organization))
        return 1
    org = org_found[0]
    org_id = org['id']
    print('* id:', org["id"])
    print('* name:', org["name"])
    return org_id


def find_uplink(baseurl, auth, site_id, wan_name):
    """Get list of uplinks for specified organization."""
    uplinks = get(baseurl + 'site/' + site_id + '/uplinks', auth=auth)
    for uplink in uplinks:
        if (wan_name in uplink['wan']):
            return uplink['id']


def find_wans(baseurl, auth, org_id):
    """Get list of WANs for specified organization."""
    wans = get(baseurl + 'org/' + org_id + '/wans', auth=auth)
    for wan in wans:
        if (wan['name'] == "Internet"):
            internet_id = wan['id']
        elif (wan['name'] == "RouteVPN"):
            routevpn_id = wan['id']
        else:
            wan_id = wan['id']
            wan_name = wan['name']

    Wan = collections.namedtuple('Wan', 'internet,routevpn,wan_id,wan_name')
    wan = Wan(internet_id, routevpn_id, wan_id, wan_name)
    return wan


def find_zones(baseurl, auth, site_id, create_sites):
    """Get list of zones for specified site."""
    zones = get(baseurl + 'site/' + site_id + '/zones', auth=auth)
    return zones


def find_sites(baseurl, auth, organization, org_id):
    """Get list of sites for specified organization."""
    print('\nGetting sites:')
    sites = get(baseurl + 'sites', auth=auth)
    sites = [site for site in sites if site['org'] == org_id]
    print(status('site', sites, "in '{0}'".format(organization)))
    return sites


def open_csv(file):
    """Import CSV file with site & network details"""
    try:
        with open(file, "rt") as f:
            reader = csv.DictReader(f)
            sites = []
            for row in reader:
                # remove whitespaces in the name column
                row['name'] = row['name'].strip(' ')
                sites.append(row)
    except IOError:
        print('Error: File {0} does not exist.'. format(file))
    else:
        return sites


def status(category, values, suffix=''):
    """Return status in human-readable format."""
    size = len(values)
    pluralization = '' if size == 1 else 's'
    return '* Found {0} {1}{2} {3}.'.format(
        size,
        category,
        pluralization,
        suffix
    )


def arguments(argv):
    """Get command line arguments."""
    description = (
        'Update SteelConnect nodes within a specified Org '
        'by copying the site name to the location field '
        'for those nodes where the location is unset.'
    )
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        'cloud_controller',
        type=str,
        help='Domain name of SteelConnect Manager',
    )
    parser.add_argument(
        'organization',
        type=str,
        help='Name of target organization',
    )
    parser.add_argument(
        '-u',
        '--username',
        help='Username for SteelConnect Manager: prompted if not supplied',
    )
    parser.add_argument(
        '-p',
        '--password',
        help='Password for SteelConnect Manager: prompted if not supplied',
    )
    parser.add_argument(
        '-f',
        '--file',
        help='CSV file to import',
    )
    return parser.parse_args()


def get_username():
    """Get username in a Python 2/3 compatible way."""
    prompt = 'Enter SCM username: '
    try:
        username = raw_input(prompt)
    except NameError:
        username = input(prompt)
    finally:
        return username


def get_password(username, password=None):
    """Get password from terminal with discretion."""
    prompt = 'Enter SCM password for {0}:'.format(username)
    while not password:
        verify = False
        while password != verify:
            if verify:
                print('Passwords do not match. Try again', file=sys.stderr)
            password = getpass.getpass(prompt)
            verify = getpass.getpass('Retype password: ')
    return password


def get(url, auth):
    """Return the items request from the SC REST API."""
    try:
        response = requests.get(url, auth=auth)
        response.raise_for_status()
    except requests.HTTPError as errh:
        print('\nERROR:', errh)
        sys.exit(1)
    except requests.ConnectionError as errc:
        print('\nERROR: Failed to connect to SCM URL, please verify URL.')
        sys.exit(1)
    except requests.RequestException as e:
        # print(e)
        print("banana")
        sys.exit(1)
    else:
        if response.status_code == 200:
            return response.json()['items']
        else:
            print('=' * 79, file=sys.stderr)
            print('Access to SteelConnect Manager failed:', file=sys.stderr)
            print(response, response.content, file=sys.stderr)
            print('=' * 79, file=sys.stderr)
            sys.exit(1)


def send(url, payload, auth, method):
    """Send to the SC REST API using either the put or post method."""
    headers = {
        'Accept': 'application/json',
        'Content-type': 'application/json',
    }
    try:
        response = method(url, auth=auth, headers=headers, data=payload)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print('HTTP {0} Error: {1}'.format(
            response.status_code,
            response.json()['error']['message'])
        )
    except requests.RequestException as e:
        print(e)
        sys.exit(1)
    return response


def put(url, payload, auth):
    """Send to the SC REST API using the PUT method."""
    return send(url, payload, auth, requests.put)


def post(url, payload, auth):
    """Send to the SC REST API using the PUT method."""
    return send(url, payload, auth, requests.post)


if __name__ == '__main__':
    result = main(sys.argv[1:])
