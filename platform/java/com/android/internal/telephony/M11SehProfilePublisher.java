/* SPDX-License-Identifier: Apache-2.0 */
package com.android.internal.telephony;

import android.telephony.TelephonyManager;
import android.telephony.data.ApnSetting;
import android.telephony.data.DataProfile;
import java.util.List;

/** Called exclusively on the DataProfileManager handler, never on a vendor Binder thread. */
public final class M11SehProfilePublisher {
    private M11SehProfilePublisher() {}

    public static void publish(Phone phone, List<DataProfile> profiles) {
        int phoneId = phone.getPhoneId();
        if (!M11SehRadioBridge.isEnabledForPhone(phoneId)) return;
        int subId = phone.getSubId();
        M11SehApnPolicy.Profile result = null;
        String operator = "";
        try {
            TelephonyManager tm = phone.getContext().getSystemService(TelephonyManager.class);
            if (tm != null) operator = tm.createForSubscriptionId(subId).getSimOperator();
            int imsCount = 0;
            for (DataProfile profile : profiles) {
                ApnSetting apn = profile.getApnSetting();
                if (apn == null || !apn.canHandleType(ApnSetting.TYPE_IMS)) continue;
                // Multiple, mixed-type, disabled, or LTE-ineligible profiles fail closed.
                imsCount++;
                if (apn.getApnTypeBitmask() != ApnSetting.TYPE_IMS || !apn.isEnabled()
                        || !apn.canSupportNetworkType(TelephonyManager.NETWORK_TYPE_LTE)) continue;
                result = new M11SehApnPolicy.Profile(apn.getApnName(),
                        ApnSetting.getProtocolStringFromInt(apn.getProtocol()),
                        ApnSetting.getProtocolStringFromInt(apn.getRoamingProtocol()),
                        apn.getUser(), apn.getPassword(), Integer.toString(apn.getAuthType()));
            }
            if (imsCount != 1 || phone.getSubId() != subId) result = null;
        } catch (RuntimeException ignored) {
            result = null;
        }
        // Even an unusable update replaces the old snapshot, so it cannot survive a SIM change.
        M11SehRadioBridge.publishSnapshot(
                new M11SehApnPolicy.Snapshot(phoneId, subId, operator, result));
    }
}
