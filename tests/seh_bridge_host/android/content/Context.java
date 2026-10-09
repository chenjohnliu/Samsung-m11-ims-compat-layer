package android.content;

public abstract class Context {
    public Context getApplicationContext() { return this; }
    public abstract ContentResolver getContentResolver();
    public abstract <T> T getSystemService(Class<T> type);
}
