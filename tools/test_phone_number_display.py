#!/usr/bin/env python3
"""Host-only validation of the SettingsLib number patch; no ROM build or ADB."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RELATIVE = 'frameworks/base/packages/SettingsLib/src/com/android/settingslib/DeviceInfoUtils.java'


def method(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        if source[end] == '{':
            depth += 1
        elif source[end] == '}':
            depth -= 1
        end += 1
    return source[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--android-root', type=Path, required=True)
    args = parser.parse_args()
    android = args.android_root.resolve()
    source_path = android / RELATIVE
    source = source_path.read_text()
    helper = method(source, 'static String getPhoneNumber(')
    single = method(source, 'public static String getFormattedPhoneNumber(')
    multiple = method(source, 'public static String getFormattedPhoneNumbers(')
    assert 'SubscriptionManager.class' in single and 'getPhoneNumber(' in single
    assert 'getFormattedPhoneNumber(context, subscriptionInfo)' in multiple
    assert 'getLine1Number()' not in single + multiple
    javac = android / 'prebuilts/jdk/jdk11/linux-x86/bin/javac'
    java = javac.with_name('java')
    sdk = android / 'prebuilts/sdk/33/public/android.jar'
    for path in (javac, java, sdk):
        if not path.is_file():
            raise SystemExit('Required existing dependency missing: ' + str(path))
    with tempfile.TemporaryDirectory(prefix='m11-number-host-') as directory:
        temp = Path(directory)
        generated = temp / 'DeviceInfoUtils.java'
        generated.write_text('package com.android.settingslib;\n'
                             'public class DeviceInfoUtils {\n' + helper + '\n}\n')
        host_classes = temp / 'host-classes'
        host_classes.mkdir()
        subprocess.run([str(javac), '-d', str(host_classes), str(generated), str(
            ROOT / 'tests/phone_number_display_host/PhoneNumberDisplayHarness.java')], check=True)
        subprocess.run([str(java), '-cp', str(host_classes),
                        'com.android.settingslib.PhoneNumberDisplayHarness'], check=True)
        # Compile the complete production source, not just the extracted helper,
        # against the real public Android 33 API. Only resource/annotation stubs
        # are provided; no Telephony API is mocked in this compilation.
        annotation = temp / 'VisibleForTesting.java'
        annotation.write_text('package androidx.annotation; public @interface VisibleForTesting {}')
        resource = temp / 'R.java'
        resource.write_text('package com.android.settingslib; public class R { '
                            'public static class string { public static final int '
                            'status_unavailable=1, oem_preferred_feedback_reporter=2; }}')
        api_classes = temp / 'api-classes'
        api_classes.mkdir()
        subprocess.run([str(javac), '-cp', str(sdk), '-d', str(api_classes),
                        str(source_path), str(annotation), str(resource)], check=True)
        print('PASS: complete DeviceInfoUtils compiles against Android 33 API')
    print('PASS: single and multiple number displays use the same source-selection path')


if __name__ == '__main__':
    main()
