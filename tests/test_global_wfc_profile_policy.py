import copy
import json
import os
from pathlib import Path
import sys
import struct
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import global_wfc_profile_policy as G


def inputs():
    mapping = [{'mccmnc': '23420', 'mnoname': 'Example_GB@BLOCKGC',
                'subset': '', 'gid1': '', 'gid2': '', 'spname': ''}]
    switches = [{'mnoname': 'Example_GB', 'enableIms': True, 'enableServiceVowifi': True}]
    profiles = [{'mnoname': 'Example_GB', 'reg_enabled': True, 'pdn': 'ims',
                 'network': [{'type': 'lte,wifi', 'services': ['mmtel'], 'enabled': True}]}]
    epdg = ET.fromstring('<iwlanapns><apn mnoname="Example_GB" connname="imsApn" apnname="ims"/>'
                         '<settings mnoname="Example_GB" epdgenable="on" is_using_certi="0"/></iwlanapns>')
    return mapping, switches, profiles, epdg


class GlobalWfcPolicyTests(unittest.TestCase):
    def test_complete_foreign_profile_is_approved_without_country_filter(self):
        approved, excluded = G.derive(*inputs())
        self.assertEqual(approved, [{'plmn': '23420', 'mnos': ['Example_GB']}])
        self.assertEqual(excluded, [])

    def test_each_stock_dependency_is_required(self):
        for part in (1, 2):
            data = list(inputs())
            data[part] = []
            self.assertEqual(G.derive(*data)[0], [])
        data = list(inputs())
        data[3].remove(data[3].find('apn'))
        self.assertEqual(G.derive(*data)[0], [])

    def test_disabled_or_missing_native_switch_is_not_coerced(self):
        for key in ('enableIms', 'enableServiceVowifi'):
            data = list(inputs())
            data[1][0][key] = False
            self.assertEqual(G.derive(*data)[0], [])

    def test_no_inheritance_guess_for_incomplete_profile(self):
        for key, value in (('pdn', None), ('reg_enabled', False), ('emergency_support', True)):
            data = list(inputs())
            data[2][0][key] = value
            self.assertEqual(G.derive(*data)[0], [])

    def test_emergency_only_profile_cannot_advertise_normal_wfc(self):
        data = list(inputs())
        data[2][0]['pdn'] = 'emergency'
        self.assertEqual(G.derive(*data)[0], [])

    def test_voice_and_wifi_network_must_be_enabled(self):
        for key, value in (('services', ['smsip']), ('type', 'lte'), ('enabled', False)):
            data = list(inputs())
            data[2][0]['network'][0][key] = value
            self.assertEqual(G.derive(*data)[0], [])

    def test_missing_apn_name_fails_closed(self):
        data = list(inputs())
        data[3].find('apn').set('apnname', '')
        self.assertEqual(G.derive(*data)[0], [])

    def test_epdg_disabled_or_unknown_certificate_is_not_assumed_supported(self):
        for key, value in (('epdgenable', 'off'), ('is_using_certi', '1')):
            data = list(inputs())
            data[3].find('settings').set(key, value)
            self.assertEqual(G.derive(*data)[0], [])

    def test_duplicate_settings_or_switch_identity_fails_closed(self):
        data = list(inputs())
        data[1].append(copy.deepcopy(data[1][0]))
        self.assertEqual(G.derive(*data)[0], [])
        data = list(inputs())
        data[3].append(copy.deepcopy(data[3].find('settings')))
        self.assertEqual(G.derive(*data)[0], [])

    def test_filtered_only_mvno_is_not_promoted_to_entire_plmn(self):
        for field in G.FILTERS:
            data = list(inputs())
            data[0][0][field] = '123'
            self.assertEqual(G.derive(*data)[0], [])

    def test_supported_parent_with_unsupported_mvno_is_not_broadly_enabled(self):
        data = list(inputs())
        data[0].append(dict(data[0][0], mnoname='Unsupported_MVNO', gid1='AB'))
        approved, excluded = G.derive(*data)
        self.assertEqual(approved, [])
        self.assertTrue(excluded[0]['has_supported_variant'])

    def test_supported_variants_under_supported_generic_mapping_are_allowed(self):
        data = list(inputs())
        data[0].append(dict(data[0][0], gid1='AB'))
        self.assertEqual(len(G.derive(*data)[0]), 1)

    def test_invalid_and_ambiguous_numeric_plmns_are_not_enabled(self):
        data = list(inputs())
        data[0][0]['mccmnc'] = '2342x'
        self.assertEqual(G.derive(*data)[0], [])
        data = list(inputs())
        data[0] = [dict(data[0][0], mccmnc=plmn) for plmn in ('23401', '234001')]
        self.assertEqual(G.derive(*data)[0], [])

    def test_unknown_mno_suffix_is_not_silently_reinterpreted(self):
        data = list(inputs())
        data[0][0]['mnoname'] = 'Example_GB@OTHER'
        self.assertEqual(G.derive(*data)[0], [])

    def test_renderer_preserves_existing_carrier_policy_without_copying_it(self):
        array = (b'        <string-array name="iwlan_handover_policy_string_array" num="2">\n'
                 b'            <item value="source=IWLAN, target=EUTRAN, type=disallowed, capabilities=IMS"/>\n'
                 b'            <item value="source=GERAN|UTRAN|EUTRAN|NGRAN|IWLAN, target=GERAN|UTRAN|EUTRAN|NGRAN|IWLAN, type=allowed"/>\n'
                 b'        </string-array>\n')
        def carrier(mnc):
            return (f'    <carrier_config mcc="466" mnc="{mnc}">\n'.encode() + array
                    + b'        <boolean name="carrier_wfc_ims_available_bool" value="true"/>\n'
                    + b'    </carrier_config>\n')
        base = b'<carrier_config_list>\n' + b''.join(carrier(mnc) for mnc in ('97', '01', '05', '92')) + b'</carrier_config_list>\n'
        with mock.patch.object(G, 'BASE_SHA', G.sha(base)):
            result = ET.fromstring(G.render(base, [{'plmn': plmn} for plmn in
                                                   ('46601', '46605', '46692', '46697', '23420')]))
        existing = result.find("carrier_config[@mcc='466']")
        foreign = result.find("carrier_config[@mcc='234']")
        self.assertIsNone(existing.find('string-array'))
        self.assertEqual(existing.find(f"boolean[@name='{G.WFC}']").get('value'), 'true')
        self.assertEqual(result.find("carrier_config[@mcc='466'][@mnc='01']").find(
            f"boolean[@name='{G.WFC}']").get('value'), 'true')
        self.assertIsNone(foreign.find('string-array'))
        self.assertEqual(foreign.find(f"boolean[@name='{G.WFC}']").get('value'), 'true')
        self.assertEqual(foreign.find("boolean[@name='carrier_default_wfc_ims_enabled_bool']").get('value'), 'false')
        self.assertTrue(all(row.get('mcc') for row in result.findall(f"carrier_config/boolean[@name='{G.WFC}']/..")))
        self.assertFalse(any('provision' in row.get('name', '') for row in result.iter()))

    def test_renderer_refuses_baseline_drift_or_loss_of_existing_support(self):
        with self.assertRaises(ValueError):
            G.render(b'<carrier_config_list/>', [])
        base = b'<carrier_config_list><carrier_config mcc="466" mnc="97"/></carrier_config_list>'
        with mock.patch.object(G, 'BASE_SHA', G.sha(base)), self.assertRaises(ValueError):
            G.render(base, [])

    def test_committed_matrix_has_93_plmns_and_only_taiwan_framework_rules_removed(self):
        policy, vendor = G.artifacts()
        tree = ET.fromstring(vendor)
        self.assertEqual(policy['policy'], 'global-stock-profile-v2')
        self.assertEqual(len(policy['approved']), 93)
        self.assertEqual(len({row['plmn'][:3] for row in policy['approved']}), 33)
        self.assertTrue({'46601', '46605', '46692', '46697'} <= {r['plmn'] for r in policy['approved']})
        taiwan = {row.get('mnc'): row for row in tree.findall("carrier_config[@mcc='466']")}
        self.assertEqual(set(taiwan), {'01', '05', '92', '97'})
        for row in taiwan.values():
            self.assertIsNone(row.find('string-array'))
            self.assertEqual(row.find(f"boolean[@name='{G.WFC}']").get('value'), 'true')
            self.assertEqual(row.find("boolean[@name='carrier_default_wfc_ims_enabled_bool']").get('value'), 'false')
            self.assertEqual([node.text for node in row.findall('string')], ['com.sec.epdg'] * 3)
        self.assertFalse(any(row.find('string-array') is not None
                             for row in tree.findall('carrier_config') if row.get('mcc') != '466'))
        self.assertEqual(tree.find("carrier_config/boolean[@name='m11q_active_call_w2l_handover_bool']").get('value'), 'false')
        for row in tree.findall('carrier_config'):
            if row.find(f"boolean[@name='{G.WFC}']") is not None:
                self.assertTrue(row.get('mcc') and row.get('mnc'))
        self.assertEqual(G.verify_tree(tree)['approved_plmns'], 93)

    def test_compiled_integer_mnc_is_accepted_but_missing_or_extra_carrier_rejected(self):
        _, vendor = G.artifacts()
        tree = ET.fromstring(vendor)
        for row in tree.findall('carrier_config'):
            if row.get('mnc'):
                row.set('mnc', str(int(row.get('mnc'))))
        G.verify_tree(tree)
        tree.remove(tree.find("carrier_config[@mcc='234']"))
        with self.assertRaises(ValueError):
            G.verify_tree(tree)
        tree = ET.fromstring(vendor)
        ET.SubElement(tree, 'carrier_config', {'mcc': '999', 'mnc': '99'})
        with self.assertRaises(ValueError):
            G.verify_tree(tree)

    def test_old_taiwan_only_overlay_and_wildcard_enable_are_rejected(self):
        _, vendor = G.artifacts()
        tree = ET.fromstring(vendor)
        for row in list(tree):
            if row.get('mcc') not in ('466', None):
                tree.remove(row)
        with self.assertRaises(ValueError):
            G.verify_tree(tree)
        tree = ET.fromstring(vendor)
        ET.SubElement(ET.SubElement(tree, 'carrier_config'), 'boolean', {'name': G.WFC, 'value': 'true'})
        with self.assertRaises(ValueError):
            G.verify_tree(tree)

    def test_contract_and_profile_input_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'policy.json'
            contract = json.loads(G.DEFAULT_CONTRACT.read_text())
            contract['vendor_sha256'] = '0' * 64
            path.write_text(json.dumps(contract))
            with self.assertRaises(ValueError):
                G.artifacts(path)
        contract, _ = G.artifacts()
        with mock.patch.object(G, 'input_data', return_value=({}, inputs())), self.assertRaises(ValueError):
            G.verify_inputs('.', contract)

    def test_apply_is_scoped_preserves_backup_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            android = Path(tmp) / 'android'
            target = android / G.VENDOR
            target.parent.mkdir(parents=True)
            original, candidate = b'baseline\n', b'candidate\n'
            target.write_bytes(original)
            target.chmod(0o640)
            backup = Path(tmp) / 'backup'
            policy = {'approved': []}
            with mock.patch.object(G, 'BASE_SHA', G.sha(original)), \
                    mock.patch.object(G, 'artifacts', return_value=(policy, candidate)), \
                    mock.patch.object(G, 'verify_inputs'):
                G.apply(android, backup)
                self.assertEqual(target.read_bytes(), candidate)
                self.assertEqual((backup / 'vendor.xml').read_bytes(), original)
                if os.name != 'nt':
                    self.assertEqual(target.stat().st_mode & 0o777, 0o640)
                G.apply(android, backup)
                self.assertEqual((backup / 'vendor.xml').read_bytes(), original)
                target.write_bytes(b'unrelated edit\n')
                with self.assertRaises(ValueError):
                    G.apply(android, Path(tmp) / 'other')
                self.assertEqual(target.read_bytes(), b'unrelated edit\n')

    def test_apply_accepts_only_pinned_prior_generated_vendor_for_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            android = Path(tmp) / 'android'
            target = android / G.VENDOR
            target.parent.mkdir(parents=True)
            target.write_bytes(bytes.fromhex('3c' * 8))
            backup = Path(tmp) / 'backup'
            policy = {'approved': []}
            with mock.patch.object(G, 'artifacts', return_value=(policy, b'candidate')), \
                    mock.patch.object(G, 'verify_inputs'), mock.patch.object(G, 'verify_source'):
                with mock.patch.object(G, 'PRIOR_VENDOR_SHA', G.sha(target.read_bytes())):
                    G.apply(android, backup)
            self.assertEqual(target.read_bytes(), b'candidate')
            self.assertEqual((backup / 'vendor.xml').read_bytes(), bytes.fromhex('3c' * 8))
            target.write_bytes(b'arbitrary drift')
            with mock.patch.object(G, 'artifacts', return_value=(policy, b'candidate')), \
                    mock.patch.object(G, 'verify_inputs'):
                with self.assertRaises(ValueError):
                    G.apply(android, Path(tmp) / 'other')

    def test_committed_historical_baseline_retains_exact_generation_pin_and_old_vendor_pin(self):
        baseline = ROOT / 'platform/carrierconfig/taiwan-legacy-baseline-vendor.xml'
        self.assertEqual(G.sha(baseline.read_bytes()), G.BASE_SHA)
        self.assertEqual(G.PRIOR_VENDOR_SHA, '4d5750cb8c60e67f9d140b40914ac763854a28c039d9c203e71e3b9932f4c38a')

    def test_binary_xml_preserves_compiled_string_text_in_both_encodings(self):
        import legacy_iwlan_trial as legacy
        from test_legacy_iwlan_trial import binary_vendor, chunk
        for encoding, value_size in (('utf8', 0), ('utf16', 0), ('utf8', 8), ('utf16', 8)):
            original = binary_vendor(encoding)
            pos = 8
            while pos < len(original):
                kind, _, size = struct.unpack_from('<HHI', original, pos)
                if kind == 0x102 and struct.unpack_from('<I', original, pos + 20)[0] == 9:
                    insertion = pos + size
                    break
                pos += size
            text = chunk(0x104, 16, struct.pack('<II', 1, 0xffffffff)
                         + struct.pack('<IHBBI', 14, value_size, 0,
                                       3 if value_size else 0, 14 if value_size else 0))
            data = bytearray(original[:insertion] + text + original[insertion:])
            struct.pack_into('<I', data, 4, len(data))
            tree = legacy.binary_xml(data)
            self.assertEqual(tree.find('carrier_config/boolean').text, 'true')
            legacy.validate_vendor(tree)

    def test_wrong_service_binding_text_is_rejected(self):
        _, vendor = G.artifacts()
        tree = ET.fromstring(vendor)
        tree.find("carrier_config/string").text = 'wrong.provider'
        with self.assertRaises(ValueError):
            G.verify_tree(tree)


if __name__ == '__main__':
    unittest.main()
