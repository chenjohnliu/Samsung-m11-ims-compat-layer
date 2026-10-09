package android.database;

public interface Cursor extends AutoCloseable {
    boolean moveToFirst();
    boolean moveToNext();
    String getString(int column);
    int getInt(int column);
    boolean isNull(int column);
    @Override void close();
}
