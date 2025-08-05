mod signals;

#[no_mangle]
pub extern "C" fn start_signal() -> i32 {
    signals::start_signal()
}

#[no_mangle]
pub extern "C" fn stop_signal() {
    signals::stop_signal();
}

// JNI interface for Java
#[cfg(target_os = "linux")]
#[cfg(any(target_arch = "x86", target_arch = "x86_64"))]
pub mod jni {
    use jni::objects::{JClass};
    use jni::sys::jint;
    use jni::JNIEnv;

    #[no_mangle]
    pub extern "system" fn Java_EnergySignal_startSignal(
        _env: JNIEnv,
        _class: JClass,
    ) -> jint {
        crate::signals::start_signal()
    }

    #[no_mangle]
    pub extern "system" fn Java_EnergySignal_stopSignal(
        _env: JNIEnv,
        _class: JClass,
    ) {
        crate::signals::stop_signal();
    }
}
