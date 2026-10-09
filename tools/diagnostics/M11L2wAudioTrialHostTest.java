/** Host-only policy regression: does not call Android or any Binder API. */
public final class M11L2wAudioTrialHostTest {
    private static void check(boolean value) { if (!value) throw new AssertionError(); }
    public static final class Profile {
        final boolean emergency;
        final int cmc;
        Profile(boolean emergency, int cmc) { this.emergency = emergency; this.cmc = cmc; }
        public boolean hasEmergencySupport() { return emergency; }
        public int getCmcType() { return cmc; }
    }
    public static final class Registration {
        final int phone, rat, pdn;
        final boolean epdg, mmtel;
        final Profile profile;
        Registration(int phone, int rat, int pdn, boolean epdg, boolean mmtel, Profile profile) {
            this.phone = phone; this.rat = rat; this.pdn = pdn;
            this.epdg = epdg; this.mmtel = mmtel; this.profile = profile;
        }
        public int getPhoneId() { return phone; }
        public int getNetworkType() { return pdn; }
        public int getCurrentRat() { return rat; }
        public boolean getEpdgStatus() { return epdg; }
        public boolean hasService(String service) { return mmtel && "mmtel".equals(service); }
        public Profile getImsProfile() { return profile; }
    }
    public static void main(String[] args) throws Exception {
        check(M11L2wAudioTrial.singleNormalCall(new int[] {1, 0, 0, 0}));
        check(!M11L2wAudioTrial.singleNormalCall(null));
        check(!M11L2wAudioTrial.singleNormalCall(new int[] {1, 0, 0}));
        check(!M11L2wAudioTrial.singleNormalCall(new int[] {0, 0, 0, 0}));
        check(!M11L2wAudioTrial.singleNormalCall(new int[] {2, 0, 0, 0}));
        check(!M11L2wAudioTrial.singleNormalCall(new int[] {1, 1, 0, 0}));
        check(!M11L2wAudioTrial.singleNormalCall(new int[] {1, 0, 1, 0}));
        check(!M11L2wAudioTrial.singleNormalCall(new int[] {1, 0, 0, 1}));
        check(M11L2wAudioTrial.noCall(new int[] {0, 0, 0, 0}));
        check(!M11L2wAudioTrial.noCall(new int[] {1, 0, 0, 0}));
        check(!M11L2wAudioTrial.noCall(null));
        Profile normal = new Profile(false, 0);
        check(M11L2wAudioTrial.normalIwlanRegistration(new Registration(0, 18, 11, true, true, normal)));
        // PDN and RAT must not be conflated, even when PDN happens to equal IWLAN's RAT.
        check(!M11L2wAudioTrial.normalIwlanRegistration(new Registration(0, 13, 11, true, true, normal)));
        check(!M11L2wAudioTrial.normalIwlanRegistration(new Registration(0, 13, 18, true, true, normal)));
        check(!M11L2wAudioTrial.normalIwlanRegistration(new Registration(1, 18, 11, true, true, normal)));
        check(!M11L2wAudioTrial.normalIwlanRegistration(new Registration(0, 18, 11, false, true, normal)));
        check(!M11L2wAudioTrial.normalIwlanRegistration(new Registration(0, 18, 11, true, false, normal)));
        check(!M11L2wAudioTrial.normalIwlanRegistration(new Registration(0, 18, 11, true, true, new Profile(true, 0))));
        check(!M11L2wAudioTrial.normalIwlanRegistration(new Registration(0, 18, 11, true, true, new Profile(false, 1))));
        check(!M11L2wAudioTrial.normalIwlanRegistration(new Registration(0, 18, 11, true, true, null)));
        check(!M11L2wAudioTrial.normalIwlanRegistration(null));
        System.out.println("PASS: 11 call-count and 10 registration gate checks (no device calls)");
    }
}
