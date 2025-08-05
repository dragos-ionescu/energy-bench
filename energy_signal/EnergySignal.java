public class EnergySignal {
    static {
        System.loadLibrary("energy_signal");
    }

    public native int startSignal();

    public native void stopSignal();
}
