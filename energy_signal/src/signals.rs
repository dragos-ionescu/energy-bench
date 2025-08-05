use once_cell::sync::Lazy;
use std::{
    env,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Once,
    },
};
use nix::libc;
use nix::sys::signal::{raise, sigaction, SigAction, SigHandler, SaFlags, SigSet, Signal};

extern "C" fn handle_signal(_: libc::c_int) {}

static HANDLER_INIT: Once = Once::new();

fn init_signal_handler() {
    HANDLER_INIT.call_once(|| {
        let sa = SigAction::new(
            SigHandler::Handler(handle_signal),
            SaFlags::empty(),
            SigSet::empty(),
        );
        unsafe {
            sigaction(Signal::SIGUSR1, &sa).unwrap();
            sigaction(Signal::SIGUSR2, &sa).unwrap();
        }
    });
}

static ITERATIONS: Lazy<usize> = Lazy::new(|| {
    env::var("ITERATIONS")
        .ok()
        .and_then(|s| s.parse::<usize>().ok())
        .unwrap_or(1)
});

static ITERATION_COUNT: AtomicUsize = AtomicUsize::new(0);

pub fn start_signal() -> i32 {
    init_signal_handler();

    let curr = ITERATION_COUNT.fetch_add(1, Ordering::SeqCst);
    if curr < *ITERATIONS {
        raise(Signal::SIGUSR1).unwrap();
        1
    } else {
        0
    }
}

pub fn stop_signal() {
    init_signal_handler();

    let curr = ITERATION_COUNT.load(Ordering::SeqCst);
    if curr > 0 && curr <= *ITERATIONS {
        raise(Signal::SIGUSR2).unwrap();
    }
}
