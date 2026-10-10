#!/usr/bin/env python3
"""Generate/verify profile-backed WFC overrides without a ROM build or downloads."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from audit_vowifi_carriers import read_apk_json

ROOT = Path(__file__).resolve().parents[1]
POLICY = 'global-stock-profile-v2'
BASE_SHA = '164515303794e27f4b7bf0ec2c52b20deea504ba52a7fe037dc869c6297cecea'
# One-time migration source accepted alongside the historical BASE_SHA.
PRIOR_VENDOR_SHA = '4d5750cb8c60e67f9d140b40914ac763854a28c039d9c203e71e3b9932f4c38a'
VENDOR = 'device/samsung/m11q/overlay/packages/apps/CarrierConfig/res/xml/vendor.xml'
APK = 'device/samsung/m11q/ims/proprietary/priv-app/imsservice/imsservice.apk'
EPDG = 'device/samsung/m11q/ims/proprietary/etc/epdg_apns_conf.xml'
DEFAULT_CONTRACT = ROOT / 'devices/m11q/global-wfc-profile-policy.json'
DEFAULT_VENDOR = ROOT / 'platform/carrierconfig/global-profile-vendor.xml'
WFC = 'carrier_wfc_ims_available_bool'
TRIAL = 'm11q_active_call_w2l_handover_bool'
SERVICES = ('carrier_data_service_wlan_package_override_string',
            'carrier_network_service_wlan_package_override_string',
            'carrier_qualified_networks_service_package_override_string')
FILTERS = ('subset', 'gid1', 'gid2', 'spname')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def mno_name(value):
    # Only this stock suffix is not part of the IMS/ePDG MNO identity.
    return value.removesuffix('@BLOCKGC')


def unique_by_mno(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.get('mnoname', '')].append(row)
    return {mno: values[0] for mno, values in grouped.items() if len(values) == 1}


def derive(mappings, switches, profiles, epdg):
    switches = unique_by_mno(switches)
    settings = unique_by_mno([dict(row.attrib) for row in epdg.iter('settings')])
    apns = {row.get('mnoname') for row in epdg.iter('apn')
            if row.get('connname') == 'imsApn' and row.get('apnname')}
    voice_mnos = {row.get('mnoname') for row in profiles
                  if row.get('reg_enabled') is True and row.get('pdn') == 'ims'
                  and row.get('emergency_support') is not True
                  and any('wifi' in network.get('type', '').split(',')
                          and 'mmtel' in network.get('services', [])
                          and network.get('enabled') is True
                          for network in row.get('network', []))}
    supported = {mno for mno in voice_mnos & apns & settings.keys()
                 if switches.get(mno, {}).get('enableIms') is True
                 and switches[mno].get('enableServiceVowifi') is True
                 and settings[mno].get('epdgenable') == 'on'
                 # Do not assume carrier-specific CA files are deployed/valid.
                 and settings[mno].get('is_using_certi', '0') == '0'}
    groups = defaultdict(list)
    for row in mappings:
        plmn = row.get('mccmnc', '')
        if re.fullmatch(r'[0-9]{5,6}', plmn):
            groups[plmn].append(row)
    approved, excluded = [], []
    for plmn, rows in sorted(groups.items()):
        mnos = sorted({mno_name(row.get('mnoname', '')) for row in rows})
        # Samsung's subset/GID selectors differ from Android's exact/regex
        # filters. A PLMN-wide override is valid only when a supported generic
        # mapping exists AND every mapped variant also has complete support.
        if not any(not any(row.get(key) for key in FILTERS) for row in rows):
            reason = 'filtered-only-mapping'
        elif not set(mnos) <= supported:
            reason = 'incomplete-or-certificate-dependent-variant'
        else:
            approved.append({'plmn': plmn, 'mnos': mnos})
            continue
        excluded.append({'plmn': plmn, 'reason': reason,
                         'has_supported_variant': bool(set(mnos) & supported)})
    # Compiled XML can encode numeric attributes as integers. Reject ambiguous
    # 2/3-digit MNC spellings instead of letting a product gate guess identity.
    numeric = defaultdict(list)
    for row in approved:
        numeric[(row['plmn'][:3], int(row['plmn'][3:]))].append(row)
    collisions = {row['plmn'] for values in numeric.values() if len(values) > 1 for row in values}
    excluded += [{'plmn': plmn, 'reason': 'numeric-mnc-collision',
                  'has_supported_variant': True} for plmn in sorted(collisions)]
    return [row for row in approved if row['plmn'] not in collisions], sorted(excluded, key=lambda r: r['plmn'])


def render(base, approved):
    if sha(base) != BASE_SHA:
        raise ValueError('vendor baseline drift; nothing generated')
    root = ET.fromstring(base)
    existing = {row.get('mcc', '') + row.get('mnc', '') for row in root.findall('carrier_config')}
    allowed = {row['plmn'] for row in approved}
    if not existing <= allowed:
        raise ValueError('existing carrier lost stock support; review instead of silently removing it')
    text = base.decode().replace(
        '<!-- Samsung-profile-backed ePDG allowlist; unknown carriers fail closed. -->',
        '<!-- Generated global stock-profile policy; no country filter or wildcard WFC enable. -->')
    text = text.replace(
        '<!-- Force a fresh WWAN IMS bearer after leaving IWLAN. This intentionally\n'
        '         trades active VoWiFi call continuity for clean post-WFC IMS state. -->',
        '<!-- Obsolete Taiwan framework IWLAN-to-EUTRAN blocking rules removed. -->')
    # Remove only the exact historical two-item framework policy, and only
    # from the four approved Taiwan carrier selectors. All other config stays.
    policy_array = re.compile(
        r'        <string-array name="iwlan_handover_policy_string_array" num="2">\n'
        r'            <item value="source=IWLAN, target=EUTRAN, type=disallowed, capabilities=IMS"/>\n'
        r'            <item value="source=GERAN\|UTRAN\|EUTRAN\|NGRAN\|IWLAN, target=GERAN\|UTRAN\|EUTRAN\|NGRAN\|IWLAN, type=allowed"/>\n'
        r'        </string-array>\n')
    taiwan_selectors = {'01', '05', '92', '97'}
    removed = 0
    carrier_block = re.compile(r'    <carrier_config\b[^>]*>.*?    </carrier_config>', re.S)

    def strip_taiwan_policy(match):
        nonlocal removed
        block = match.group(0)
        attrs = dict(re.findall(r'(mcc|mnc)="([^"]+)"', block.split('>', 1)[0]))
        if attrs.get('mcc') == '466' and attrs.get('mnc') in taiwan_selectors:
            block, count = policy_array.subn('', block)
            removed += count
        return block

    text = carrier_block.sub(strip_taiwan_policy, text)
    if removed != 4:
        raise ValueError('expected exact historical Taiwan policy in four carrier blocks')
    blocks = ['    <!-- Keep AP-assisted experiments off on every SIM; use stock legacy IWLAN. -->',
              '    <carrier_config>', f'        <boolean name="{TRIAL}" value="false"/>',
              '    </carrier_config>']
    for row in approved:
        plmn = row['plmn']
        if plmn in existing:
            continue
        blocks += [f'    <carrier_config mcc="{plmn[:3]}" mnc="{plmn[3:]}">',
                   f'        <boolean name="{WFC}" value="true"/>',
                   '        <boolean name="carrier_default_wfc_ims_enabled_bool" value="false"/>']
        blocks += [f'        <string name="{key}">com.sec.epdg</string>' for key in SERVICES]
        blocks += ['    </carrier_config>']
    if text.count('</carrier_config_list>') != 1:
        raise ValueError('unexpected vendor root')
    return (text.replace('</carrier_config_list>', '\n'.join(blocks) + '\n</carrier_config_list>')
            .rstrip('\n') + '\n').encode()


def input_data(apk_path, epdg_path):
    with zipfile.ZipFile(apk_path) as apk:
        names = ('mnomap', 'imsswitch', 'imsprofile')
        for name in names:
            if apk.namelist().count(f'res/raw/{name}.json') != 1:
                raise ValueError('missing/duplicate stock resource: ' + name)
        hashes = {name: sha(apk.read(f'res/raw/{name}.json')) for name in names}
        data = [read_apk_json(apk, name) for name in names]
    epdg_bytes = Path(epdg_path).read_bytes()
    hashes['epdg_apns_conf'] = sha(epdg_bytes)
    return hashes, (data[0]['mnomap'], data[1]['imsswitch'], data[2]['profile'], ET.fromstring(epdg_bytes))


def exclusions(excluded):
    return {'excluded_plmns': len(excluded),
            'excluded_reason_counts': dict(sorted(Counter(row['reason'] for row in excluded).items())),
            'excluded_candidates': [row for row in excluded if row['has_supported_variant']]}


def generate(apk, epdg, baseline, output):
    hashes, inputs = input_data(apk, epdg)
    approved, excluded = derive(*inputs)
    vendor = render(Path(baseline).read_bytes(), approved)
    contract = {'schema_version': 1, 'policy': POLICY, 'stock_firmware': 'M115FXXS5CWK3',
                'source_baseline_sha256': BASE_SHA, 'vendor_sha256': sha(vendor),
                'input_resource_sha256': hashes, 'approved': approved, **exclusions(excluded),
                'runtime_validated_outside_taiwan': False}
    output = Path(output)
    output.mkdir(exist_ok=False)
    (output / 'vendor.xml').write_bytes(vendor)
    (output / 'contract.json').write_text(json.dumps(contract, indent=2) + '\n')
    (output / 'private-exclusion-report.json').write_text(json.dumps(excluded, indent=2) + '\n')
    return {'policy': POLICY, 'approved_plmns': len(approved), 'excluded_plmns': len(excluded),
            'vendor_sha256': sha(vendor), 'rom_build_run': False}


def artifacts(contract=DEFAULT_CONTRACT, vendor=DEFAULT_VENDOR):
    policy = json.loads(Path(contract).read_text())
    data = Path(vendor).read_bytes()
    if policy.get('schema_version') != 1 or policy.get('policy') != POLICY or sha(data) != policy.get('vendor_sha256'):
        raise ValueError('global WFC policy artifact drift')
    return policy, data


def verify_inputs(android, policy):
    hashes, inputs = input_data(Path(android) / APK, Path(android) / EPDG)
    approved, excluded = derive(*inputs)
    if (hashes != policy['input_resource_sha256'] or approved != policy['approved']
            or any(policy.get(key) != value for key, value in exclusions(excluded).items())):
        raise ValueError('IMS/ePDG policy inputs changed; regenerate and review before build/flash')


def canonical(element, selectors):
    attrs = dict(element.attrib)
    if element.tag == 'carrier_config' and 'mcc' in attrs and 'mnc' in attrs:
        key = (attrs['mcc'], int(attrs['mnc']))
        if key not in selectors:
            raise ValueError('unexpected carrier selector')
        attrs['mnc'] = selectors[key]
    return (element.tag, tuple(sorted(attrs.items())), (element.text or '').strip(),
            tuple(canonical(child, selectors) for child in element))


def verify_tree(tree, contract=DEFAULT_CONTRACT, vendor=DEFAULT_VENDOR):
    policy, data = artifacts(contract, vendor)
    expected = ET.fromstring(data)
    selectors = {(row['plmn'][:3], int(row['plmn'][3:])): row['plmn'][3:] for row in policy['approved']}
    if canonical(tree, selectors) != canonical(expected, selectors):
        raise ValueError('packaged global WFC matrix mismatch; do not flash')
    return {'global_wfc_profile_policy': POLICY, 'approved_plmns': len(policy['approved'])}


def verify_source(android, contract=DEFAULT_CONTRACT, vendor=DEFAULT_VENDOR):
    policy, data = artifacts(contract, vendor)
    verify_inputs(android, policy)
    if (Path(android) / VENDOR).read_bytes() != data:
        raise ValueError('source global WFC matrix drift')
    return {'status': 'PASS', 'policy': POLICY, 'approved_plmns': len(policy['approved']), 'rom_build_run': False}


def apply(android, backup):
    import legacy_iwlan_trial as legacy
    root, backup = legacy.source_root(android), legacy.safe(backup)
    policy, data = artifacts()
    verify_inputs(root, policy)
    target = legacy.regular(root / VENDOR)
    old = target.read_bytes()
    if old == data:
        return verify_source(root)
    if sha(old) not in (BASE_SHA, PRIOR_VENDOR_SHA):
        raise ValueError('source baseline drift; no changes made')
    backup.mkdir(exist_ok=False)
    (backup / 'vendor.xml').write_bytes(old)
    legacy.atomic_replace(target, old, data)
    return verify_source(root)


def verify_product(product):
    import legacy_iwlan_trial as legacy
    product = Path(product)
    policy, _ = artifacts()
    # Verify the actually packaged input resources as well as the overlay.
    hashes, inputs = input_data(product / 'system/system_ext/priv-app/imsservice/imsservice.apk',
                                product / 'system/etc/epdg_apns_conf.xml')
    if hashes != policy['input_resource_sha256'] or derive(*inputs)[0] != policy['approved']:
        raise ValueError('packaged IMS/ePDG profile input drift; do not flash')
    with zipfile.ZipFile(product / 'vendor/overlay/CarrierConfig__auto_generated_rro_vendor.apk') as apk:
        if apk.namelist().count('res/xml/vendor.xml') != 1:
            raise ValueError('missing/duplicate compiled vendor.xml')
        data = apk.read('res/xml/vendor.xml')
        if data.lstrip().startswith(b'<'):
            raise ValueError('product overlay must contain compiled Android XML')
        result = verify_tree(legacy.binary_xml(data))
    return dict(status='PASS', rom_build_run=False, **result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('generate', 'apply', 'verify-source', 'verify-product'))
    parser.add_argument('--android-root', type=Path)
    parser.add_argument('--product-root', type=Path)
    parser.add_argument('--ims-apk', type=Path)
    parser.add_argument('--epdg-config', type=Path)
    parser.add_argument('--base-vendor', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    try:
        required = {'generate': ('ims_apk', 'epdg_config', 'base_vendor', 'output_dir'),
                    'apply': ('android_root', 'backup'), 'verify-source': ('android_root',),
                    'verify-product': ('product_root',)}[args.action]
        if any(getattr(args, key) is None for key in required):
            raise ValueError('missing required options: ' + ', '.join(required))
        if args.action == 'generate':
            result = generate(args.ims_apk, args.epdg_config, args.base_vendor, args.output_dir)
        elif args.action == 'apply':
            result = apply(args.android_root, args.backup)
        elif args.action == 'verify-source':
            result = verify_source(args.android_root)
        else:
            result = verify_product(args.product_root)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, 'error: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
