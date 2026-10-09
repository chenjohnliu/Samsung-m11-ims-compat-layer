package android.content;

import android.database.Cursor;
import android.net.Uri;

public abstract class ContentResolver {
    public abstract Cursor query(Uri uri, String[] projection, String selection,
            String[] selectionArgs, String sortOrder);
}
