#!/usr/bin/env python3
"""
Deletes all sites but the site with the name DC-Sydney.

Requires Python3 with Requests library:
- pip3 install requests

USAGE:
    steelconnect_bulk_delete.py scm.riverbed.cc organization

Based on Greg Mueller's scrap_set_node_location.py:
https://github.com/grelleum/SteelConnect/blob/master/scrap_set_node_location.py
"""

from __future__ import print_function
import argparse
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

    username = args.username if args.username else get_username()
    password = args.password if args.password else get_password(username)
    auth = (username, password)

    org_id = find_org(baseurl, auth, organization)
    sites = find_sites(baseurl, auth, organization, org_id)

    delete_sites = []
    for site in sites:
        if (site['name'] == "DC-Sydney"):
            print('\n* DC-Sydney found, not deleting that one.\n')
        else:
            delete_sites.append(site)
            # delete_site(baseurl, auth, site)

    if delete_sites:
        remove_sites(baseurl, auth, delete_sites)
        print('All done!\n')
    else:
        print('Nothing to delete.\n')


def remove_sites(baseurl, auth, sites):
    """Invoke yes_or_no to verify deletion, then delete sites."""
    yes_or_no("Are you sure you want to delete all sites?")
    while True:
        if(yes_or_no('Are you really sure? THIS CAN NOT BE UNDONE!')):
            delete_site(baseurl, auth, sites)
            break


def yes_or_no(question):
    """Ask y/n to confirm deletion of sites. """
    reply = str(input(question+' (y/n): ')).lower().strip()
    if reply[0] == 'y':
        return 1
    elif reply[0] == 'n':
        sys.exit(1)
    else:
        return yes_or_no(
            "Please enter (y/n), are you sure you want to delete all sites?")


def delete_site(baseurl, auth, sites):
    for site in sites:
        url = baseurl + 'site/' + site['id']
        response = delete(url, payload=None, auth=auth)
        print('Deleting site {0}:'.format(site['name']),
              response.status_code, response.reason)


def find_sites(baseurl, auth, organization, org_id):
    """Get list of sites for specified organization."""
    print('\nGetting sites:')
    sites = get(baseurl + 'sites', auth=auth)
    sites = [site for site in sites if site['org'] == org_id]
    print(status('site', sites, "in '{0}'".format(organization)))
    return sites


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


def delete(url, payload, auth):
    """Send to the SC REST API using the PUT method."""
    return send(url, payload, auth, requests.delete)


if __name__ == '__main__':
    result = main(sys.argv[1:])
