define install_items
	@install -d -m 755 $(2)
	@for item in $(wildcard $(1)); do \
		if [ -f "$$item" ]; then \
			install -m 644 "$$item" $(2); \
		elif [ -d "$$item" ]; then \
			rsync -a --chmod=Du=rwx,go=rx,Fu=rw,go=r "$$item/" "$(2)/$$(basename "$$item")/"; \
		fi; \
	done
endef

NAME := energy-bench
PREFIX := $(HOME)
BASE_DIR := $(PREFIX)/.$(NAME)
BIN_DIR := $(PREFIX)/.local/bin
SIG_DIR := energy_signal
SIG_SO := $(SIG_DIR)/target/release/libenergy_signal.so
SIG_A := $(SIG_DIR)/target/release/libenergy_signal.a
SIG_HEADER := $(SIG_DIR)/energy_signal.h
SIG_JNI := $(SIG_DIR)/EnergySignal.java

all: $(SIG_SO) $(SIG_A)

$(SIG_SO) $(SIG_A):
	cargo build --release --manifest-path $(SIG_DIR)/Cargo.toml

install: $(SIG_SO) $(SIG_A)
	install -d -m 755 $(BASE_DIR)
	install -d -m 755 $(BIN_DIR)
	install -m 755 $(SIG_SO) $(BASE_DIR)
	install -m 755 $(SIG_A) $(BASE_DIR)
	install -m 644 $(SIG_HEADER) $(BASE_DIR)
	install -m 644 $(SIG_JNI) $(BASE_DIR)
	@if command -v sudo >/dev/null 2>&1; then \
		sudo perf probe -d probe_libenergy_signal:start_signal 2>/dev/null || true; \
		sudo perf probe -d probe_libenergy_signal:stop_signal 2>/dev/null || true; \
		sudo perf probe -d probe_libenergy_signal:startSignal 2>/dev/null || true; \
		sudo perf probe -d probe_libenergy_signal:stopSignal 2>/dev/null || true; \
		sudo perf probe -x $(BASE_DIR)/$(notdir $(SIG_SO)) start_signal 2>/dev/null || true; \
		sudo perf probe -x $(BASE_DIR)/$(notdir $(SIG_SO)) stop_signal 2>/dev/null || true; \
		sudo perf probe -x $(BASE_DIR)/$(notdir $(SIG_SO)) startSignal=Java_EnergySignal_startSignal 2>/dev/null || true; \
		sudo perf probe -x $(BASE_DIR)/$(notdir $(SIG_SO)) stopSignal=Java_EnergySignal_stopSignal 2>/dev/null || true; \
	else \
		echo "Warning: sudo not available. Perf probes not installed."; \
		echo "Some functionality may be limited."; \
	fi
	$(call install_items,*.py,$(BASE_DIR))
	$(call install_items,workloads/*,$(BASE_DIR)/workloads)
	$(call install_items,scenarios/examples/*,$(BASE_DIR)/examples)
	$(call install_items,commands/*,$(BASE_DIR)/commands)
	$(call install_items,setups/*,$(BASE_DIR)/setups)
	$(call install_items,llms/*,$(BASE_DIR)/llms)
	install -m 644 trial.yml .env $(BASE_DIR)
	@echo '#!/bin/sh' > $(BIN_DIR)/$(NAME)
	@echo 'python3 $(BASE_DIR)/__main__.py "$$@"' >> $(BIN_DIR)/$(NAME)
	@chmod +x $(BIN_DIR)/$(NAME)

uninstall:
	rm -rf $(BASE_DIR)
	rm -f $(BIN_DIR)/$(NAME)

clean:
	cargo clean --manifest-path $(SIG_DIR)/Cargo.toml

.PHONY: all install uninstall clean
.SILENT:
