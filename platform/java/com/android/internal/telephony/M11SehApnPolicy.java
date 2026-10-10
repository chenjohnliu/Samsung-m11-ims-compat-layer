/* SPDX-License-Identifier: Apache-2.0 */
package com.android.internal.telephony;

/** Immutable APN boundary data. Never logs credentials or invents an APN/CID. */
public final class M11SehApnPolicy {
    private M11SehApnPolicy() {}

    // DSDS LoadApnProfile(type=ims, RAT=14), verified from the stock native call chain.
    public static final String IMS_SELECTION = "carrier_enabled=1"
            + " and (bearer=14 or bearer=0) and bearer_bitmask!=131072 and type LIKE '%ims%'";

    public static final class Profile {
        public final String apn, protocol, roamingProtocol, user, password, authentication;

        public Profile(String apn, String protocol, String roamingProtocol,
                String user, String password, String authentication) {
            this.apn = nonNull(apn);
            this.protocol = nonNull(protocol);
            this.roamingProtocol = nonNull(roamingProtocol);
            this.user = nonNull(user);
            this.password = nonNull(password);
            this.authentication = nonNull(authentication);
        }

        public boolean usable() {
            return !apn.isEmpty() && ipProtocol(protocol) && ipProtocol(roamingProtocol)
                    && (authentication.equals("-1") || authentication.equals("0")
                    || authentication.equals("1") || authentication.equals("2")
                    || authentication.equals("3"));
        }

        public String[] wireFields() {
            return new String[] {apn, protocol, roamingProtocol, user, password, authentication};
        }
    }

    public static final Profile EMPTY = new Profile("", "", "", "", "", "");

    public static boolean validOperator(String operator) {
        return operator != null && operator.matches("[0-9]{5,6}");
    }

    public static boolean supportedPhone(int phoneId) { return phoneId == 0 || phoneId == 1; }

    /** Created on the DataProfileManager handler; only final fields cross Binder threads. */
    public static final class Snapshot {
        public final int phoneId, subscriptionId;
        public final String operator;
        public final Profile soleImsProfile;

        public Snapshot(int phoneId, int subscriptionId, String operator, Profile soleImsProfile) {
            this.phoneId = phoneId;
            this.subscriptionId = subscriptionId;
            this.operator = nonNull(operator);
            this.soleImsProfile = soleImsProfile;
        }
    }

    public static Profile fallback(Snapshot snapshot, int phoneId, int subId,
            String operator, String selection, boolean active) {
        if (!active || !supportedPhone(phoneId) || subId < 0 || !validOperator(operator)
                || !IMS_SELECTION.equals(selection) || snapshot == null
                || snapshot.phoneId != phoneId || snapshot.subscriptionId != subId
                || !snapshot.operator.equals(operator) || snapshot.soleImsProfile == null
                || !snapshot.soleImsProfile.usable()) return EMPTY;
        return snapshot.soleImsProfile;
    }

    private static String nonNull(String value) { return value == null ? "" : value; }
    private static boolean ipProtocol(String value) {
        return value.equals("IP") || value.equals("IPV6") || value.equals("IPV4V6");
    }
}
