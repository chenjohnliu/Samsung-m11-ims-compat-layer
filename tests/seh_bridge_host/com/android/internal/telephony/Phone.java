package com.android.internal.telephony;

import android.content.Context;

public final class Phone {
    private final Context context;
    private final int phoneId;
    private int subId;
    private int contextReads;
    public Phone(Context context, int phoneId, int subId) {
        this.context = context;
        this.phoneId = phoneId;
        this.subId = subId;
    }
    public int getPhoneId() { return phoneId; }
    public int getSubId() { return subId; }
    public Context getContext() { contextReads++; return context; }
    public int contextReads() { return contextReads; }
    public void setSubId(int value) { subId = value; }
}
