import android.os.IBinder;
import android.os.Process;
import android.os.ServiceManager;
import android.os.SystemProperties;
import java.lang.reflect.Array;
import java.lang.reflect.Method;
import java.util.Arrays;

/** One-shot, manually requested use of the existing Samsung audio API. */
public final class M11L2wAudioTrial {
    private static Object call(Object target, String name) throws Exception {
        return target.getClass().getMethod(name).invoke(target);
    }
    private static void require(boolean ok, String message) {
        if (!ok) throw new IllegalStateException(message);
    }
    static boolean singleNormalCall(int[] counts) {
        return Arrays.equals(counts, new int[] {1, 0, 0, 0});
    }
    static boolean noCall(int[] counts) {
        return Arrays.equals(counts, new int[] {0, 0, 0, 0});
    }
    static boolean normalIwlanRegistration(Object reg) throws Exception {
        if (reg == null) return false;
        Object profile = call(reg, "getImsProfile");
        if (profile == null) return false;
        int phone = (Integer) call(reg, "getPhoneId");
        // Samsung getNetworkType is the PDN type (IMS=11), not the current RAT.
        int pdn = (Integer) call(reg, "getNetworkType");
        int rat = (Integer) call(reg, "getCurrentRat");
        boolean epdg = (Boolean) call(reg, "getEpdgStatus");
        boolean mmtel = (Boolean) reg.getClass().getMethod("hasService", String.class)
                .invoke(reg, "mmtel");
        boolean emergency = (Boolean) call(profile, "hasEmergencySupport");
        int cmc = (Integer) call(profile, "getCmcType");
        System.out.println("SAE_TRIAL_REG phone=" + phone + " pdn=" + pdn
                + " currentRat=" + rat + " epdg=" + epdg + " mmtel=" + mmtel
                + " emergency=" + emergency + " cmc=" + cmc);
        return phone == 0 && rat == 18 && epdg && mmtel && !emergency && cmc == 0;
    }
    public static void main(String[] args) {
        try {
            require(args.length == 2 && ("preflight".equals(args[1])
                    || "start-sae".equals(args[1])), "Expected imsmanager.jar and preflight/start-sae");
            require(Process.myUid() == 0, "Root required; no operation performed");
            require("m11q".equals(SystemProperties.get("ro.product.device")), "Not m11q");
            require("legacy".equals(SystemProperties.get("ro.telephony.iwlan_operation_mode")),
                    "Not legacy IWLAN");
            String[] operators = SystemProperties.get("gsm.sim.operator.numeric").split(",", -1);
            require(operators.length > 0 && "46697".equals(operators[0]), "Slot 0 is not TWM");
            for (int i = 1; i < operators.length; i++)
                require(operators[i].isEmpty(), "Second active SIM is outside this trial");
            IBinder binder = ServiceManager.checkService("secims");
            require(binder != null && "com.sec.ims.IImsService".equals(binder.getInterfaceDescriptor()),
                    "Unexpected secims Binder");
            // Use the phone's own typed client, not a guessed transaction number.
            ClassLoader loader = (ClassLoader) Class.forName("dalvik.system.PathClassLoader")
                    .getConstructor(String.class, ClassLoader.class)
                    .newInstance(args[0], M11L2wAudioTrial.class.getClassLoader());
            Class<?> api = loader.loadClass("com.sec.ims.IImsService");
            Object service = loader.loadClass("com.sec.ims.IImsService$Stub")
                    .getMethod("asInterface", IBinder.class).invoke(null, binder);
            Method audio = api.getMethod("changeAudioPathForSlot", int.class, int.class);
            Method count = api.getMethod("getCallCount", int.class);
            Method registrations = api.getMethod("getRegistrationInfoByPhoneId", int.class);
            int[] calls = (int[]) count.invoke(service, 0);
            int[] otherCalls = (int[]) count.invoke(service, 1);
            require(calls != null && calls.length == 4 && otherCalls != null && otherCalls.length == 4,
                    "Unexpected Samsung call-count API result");
            System.out.println("SAE_TRIAL_API_READY (read-only call counts checked; no audio request yet)");
            if ("preflight".equals(args[1])) return;
            require(singleNormalCall(calls),
                    "Expected exactly one non-video/non-downgraded/non-emergency call on slot 0");
            require(noCall(otherCalls), "Another slot has a call");
            Object regs = registrations.invoke(service, 0);
            boolean normalIwlan = false;
            if (regs != null) for (int i = 0; i < Array.getLength(regs); i++) {
                normalIwlan |= normalIwlanRegistration(Array.get(regs, i));
            }
            require(normalIwlan, "No normal slot-0 IWLAN mmtel registration");
            // Recheck the call counts immediately before the one scoped write.
            require(Arrays.equals((int[]) count.invoke(service, 0), calls), "Call changed during checks");
            require(Arrays.equals((int[]) count.invoke(service, 1), otherCalls), "Other slot changed");
            System.out.println("SAE_TRIAL_REQUEST phone=0 direction=0 count=1");
            audio.invoke(service, 0, 0);
            System.out.println("SAE_TRIAL_REQUEST_RETURNED (not proof of audio recovery)");
        } catch (Throwable e) {
            System.err.println("SAE_TRIAL_FAILED: " + e);
            System.exit(1);
        }
    }
}
