import android.os.IBinder;

/** Changes only the two stock SystemUI gesture-handle colors. */
public class GesturePillOverlay {
    public static void main(String[] args) throws Exception {
        if (android.os.Process.myUid() != 0) throw new SecurityException("Root required");
        if (args.length != 1) throw new IllegalArgumentException("Use hide or show");
        Class<?> identifier = Class.forName("android.content.om.OverlayIdentifier");
        Object id = identifier.getConstructor(String.class,String.class).newInstance("android","CodexGesturePill");
        Class<?> transaction = Class.forName("android.content.om.OverlayManagerTransaction");
        Class<?> builder = Class.forName("android.content.om.OverlayManagerTransaction$Builder");
        Object t = builder.getConstructor().newInstance();
        if (args[0].equals("hide")) {
            Class<?> overlay = Class.forName("android.content.om.FabricatedOverlay");
            Class<?> fb = Class.forName("android.content.om.FabricatedOverlay$Builder");
            Object b = fb.getConstructor(String.class,String.class,String.class)
                .newInstance("android","CodexGesturePill","com.android.systemui");
            for (String color : new String[]{"dark","light"}) {
                fb.getMethod("setResourceValue",String.class,int.class,int.class).invoke(b,
                    "com.android.systemui:color/navigation_bar_home_handle_"+color+"_color",0x1c,0);
            }
            builder.getMethod("registerFabricatedOverlay",overlay).invoke(t,fb.getMethod("build").invoke(b));
            builder.getMethod("setEnabled",identifier,boolean.class,int.class).invoke(t,id,true,0);
        } else if (args[0].equals("show")) {
            builder.getMethod("unregisterFabricatedOverlay",identifier).invoke(t,id);
        } else throw new IllegalArgumentException("Use hide or show");
        Object binder = Class.forName("android.os.ServiceManager").getMethod("getService",String.class).invoke(null,"overlay");
        Object manager = Class.forName("android.content.om.IOverlayManager$Stub").getMethod("asInterface",IBinder.class).invoke(null,binder);
        Class.forName("android.content.om.IOverlayManager").getMethod("commit",transaction).invoke(manager,builder.getMethod("build").invoke(t));
        System.out.println("Gesture pill overlay: "+args[0]);
        System.exit(0);
    }
}
