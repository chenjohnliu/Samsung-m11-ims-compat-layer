#!/system/bin/sh

echo '=== ROOT_IDENTITY ==='
id
getenforce
date

echo '=== LSHAL ==='
lshal

echo '=== PROCESSES ==='
ps -AZ -o USER,PID,PPID,NAME,ARGS

echo '=== RILD_MAPS ==='
for p in $(pidof rild); do
    echo "---PID:$p---"
    tr '\000' ' ' < "/proc/$p/cmdline"
    echo
    grep -Ei 'libsec-ril|libril_sem|vendor.samsung.hardware.radio.(channel|bridge)|libsecril|libqmi|libril' "/proc/$p/maps"
done

echo '=== BACKEND_FILES ==='
for f in \
    /vendor/lib/libsec-ril.so \
    /vendor/lib/libril_sem.so \
    /vendor/lib/vendor.samsung.hardware.radio.channel@2.0.so \
    /vendor/lib/vendor.samsung.hardware.radio.bridge@2.0.so \
    /system/lib/vendor.samsung.hardware.radio.channel@2.0.so \
    /system/lib/vendor.samsung.hardware.radio.bridge@2.0.so; do
    ls -lZ "$f" 2>&1
    sha256sum "$f" 2>/dev/null
done

echo '=== INIT_AND_SOCKETS ==='
getprop | grep -E '\[init\.svc\.(imsd|epdgd|rild)|\[ril\.'
ls -lZ /dev/socket | grep -Ei 'ims|epdg|ril'

echo '=== IMS_PROCESSES_AND_PACKAGES ==='
ps -AZ | grep -Ei 'ims|epdg|rild'
pm list packages -f | grep -Ei 'ims|epdg'

echo '=== RELEVANT_AVC ==='
logcat -b all -d -v threadtime | grep -Ei 'avc:.*(ims|epdg|rild|radio|hal_telephony)'
