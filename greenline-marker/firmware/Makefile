# GreenLine GL-1 firmware - host tests and cross-compile check.
#
#   make test    build everything for the host with
#                gcc -std=c99 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror
#                and run every tests/test_*.c executable
#   make asan    the same under -fsanitize=address,undefined,float-cast-overflow
#   make cross   compile core/, drivers/ and app/ (NOT hal/stm32u5, NOT hal/host)
#                with arm-none-eabi-gcc for the Cortex-M33 and print the size
#                table, the largest stack frames, the forbidden-symbol check
#                (on the objects AND on a link probe against the toolchain's
#                libm / libc) and the fused-instruction check
#   make config  regenerate core/gl_config.h, core/gl_font_data.c,
#                hal/stm32u5/gl_pins.h and tests/solver/gl_solver_vectors.c
#   make pins    regenerate hal/stm32u5/gl_pins.h from the netlist's pin map
#                ../electrical/gl1_main/pinmap.json (its single input; the
#                layout step may still exchange pins: this is the one
#                command that follows it)
#   make pins-check
#                fail if hal/stm32u5/gl_pins.h is stale against pinmap.json,
#                or if the generator no longer refuses the defects its
#                self-test seeds into a copy of the pin map (part of
#                config-check, and with it of every test and cross build)
#   make diff    NOT part of `make test`: build the solver as shared libraries
#                (double and single precision) and run tools/diff_solver.py,
#                the differential test against the Python reference in
#                ../sim on DIFF_N (default 20000) random reads and as many
#                random aim problems.  Needs python3 with numpy, scipy and
#                the reference's own dependencies.
#   make bench   NOT part of `make test`: trial rolls, RK4 steps and fit
#                iterations of typical and worst-case estimates
#                (tools/solver_bench.c, single precision)
#   make appdiff NOT part of `make test`: run tests/test_e2e_putt (the whole
#                firmware on the simulator), dump every gl_measurements_t
#                record the application handed to the estimator, and run
#                the PYTHON reference on the same records
#                (tools/app_diff.py)
#   make cross-hal STM32_HEADERS=<dir>
#                compile (ONLY compile) hal/stm32u5/gl_hal_stm32u5.c against
#                the vendor's header files in <dir>; skipped with a message
#                without them
#   make boot-cross [STM32_HEADERS=<dir>]
#                the boot stub of DESIGN_SPEC E34 (boot/): its portable part
#                with the cross flags; with the vendor's device header it is
#                also linked (no library) and must fit its 8 kB page
#   make release-gate
#                exit 1 while the USB ids (app/gl_usb_ids.h) or the regulatory
#                text of the INFO screen (app/gl_regulatory.h) are the named
#                placeholders; RELEASE=1 makes every build fail the same way
#   make tooltest / make replay-demo / make glsim
#                NOT part of `make test`: the PC tool tools/glctl against the
#                firmware on the host simulator (build/host/glsim), the replay
#                of logged reads through the Python reference
#   make bench-vision / make profile
#                NOT part of `make test`: what a read costs (cost table of the
#                simulator; callgrind)
#   make steep-sweep
#                NOT part of `make test`: the sweep the "TOO STEEP" threshold
#                of DESIGN_SPEC E31 was chosen from (tools/steep_sweep.py)
#   make readme-logs
#                run test, cross, appdiff, tooltest, replay-demo, bench-vision,
#                bench, diff, steep-sweep and asan (and cross-hal / boot-cross
#                if STM32_HEADERS is set) and keep their output in
#                build/readme/ - about half an hour
#   make readme-check
#                NEEDS `make readme-logs` FIRST (it runs nothing; `make clean`
#                deletes the logs).  Compares every figure README.md quotes through
#                tools/readme_check.py with those logs; fails on a difference
#                (`python3 tools/readme_check.py --update` rewrites the
#                generated blocks of the README from the logs)
#   make clean
#
# Layout rules the wildcards rely on:
#   core/*.c      portable core            (no HAL, no stdio)
#   drivers/*.c   device drivers           (include only hal/gl_hal.h + core)
#   app/*.c       main loop and glue       (app/gl_main.c holds main() and is
#                                           left out of the host test library)
#   hal/host/*.c  host simulator backend of hal/gl_hal.h
#   hal/stm32u5/  STM32U585 backend: compiled only by `make cross-hal`
#                 (against vendor headers that are not in this repository);
#                 its generated pin table gl_pins.h is checked by
#                 tests/test_pins.c
#   tests/synth/*.c  synthetic data generators shared by tests
#   tests/solver/    reference vectors of the solver (generated) and the
#                    harness that runs them; see "the solver in two
#                    precisions" below
#   tests/test_*.c   one executable each, each with its own main()
#
# The solver in two precisions.  core/gl_solver*.c is written against
# gl_real_t.  The firmware build (and `make cross`) compiles it as it is:
# single precision.  The host test library ALSO holds the same files compiled
# with -DGL_SOLVER_DOUBLE (objects under core64/, symbols gl_solver64_*), the
# build that is compared digit by digit with the Python reference, and
# tests/solver/gl_solver_run.c is compiled once for each (solver/ and
# solver64/).  tests/solver/gl_solver_ref.c exists in the double flavour only:
# the end-to-end tests use it as the reference for the records the application
# builds.  Nothing compiled with -DGL_SOLVER_DOUBLE reaches the target.

HOSTCC   ?= gcc
CROSS    ?= arm-none-eabi-
PYTHON   ?= python3
# V=1 shows the full compiler command lines.
V        ?= 0
ifeq ($(V),1)
Q :=
else
Q := @
endif

# -ffp-contract=off: no fused multiply-add anywhere.  The solver's single-
# precision results are compared with the reference operation by operation;
# a contracted a * b + c rounds once instead of twice.  -std=c99 implies it
# with gcc, -std=gnu99 does not: it is stated, and `make cross` checks the
# objects for fused instructions.
WARN     := -std=c99 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror -ffp-contract=off
# Extra checks for firmware code (core, drivers, app): no silent double
# arithmetic, no variable-length arrays, every global function declared.
FW_WARN  := -Wdouble-promotion -Wvla -Wmissing-prototypes -Wstrict-prototypes -Wundef
INC      := -Icore -Idrivers -Ihal -Ihal/host -Ihal/stm32u5 -Iapp -Iboot -Itests -Itests/synth \
            -Itests/solver -Itests/vision_ref

# RELEASE=1: a release build.  It defines GL_RELEASE_BUILD for every compiler
# invocation, and app/gl_usb_ids.h then stops the build while the USB vendor
# and product ids are the named placeholders (DESIGN_SPEC E34: none is
# assigned), as does app/gl_regulatory.h while the regulatory text of the INFO
# screen is its placeholder.  `make release-gate` asks both questions alone.
RELEASE  ?= 0
ifeq ($(RELEASE),1)
RELDEF   := -DGL_RELEASE_BUILD
else
RELDEF   :=
endif

CORE_SRC    := $(sort $(wildcard core/*.c))
DRV_SRC     := $(sort $(wildcard drivers/*.c))
APP_SRC     := $(sort $(wildcard app/*.c))
APP_LIB_SRC := $(filter-out app/gl_main.c,$(APP_SRC))
HOSTHAL_SRC := $(sort $(wildcard hal/host/*.c))
SYNTH_SRC   := $(sort $(wildcard tests/synth/*.c))
TEST_SRC    := $(sort $(wildcard tests/test_*.c))

SOLVER_SRC  := $(sort $(wildcard core/gl_solver*.c))
SOLVERT_SRC := tests/solver/gl_solver_vectors.c tests/solver/gl_solver_run.c
# the phase-1 vision code, frozen: the oracle of tests/test_vision_equiv.c
VISREF_SRC  := tests/vision_ref/gl_vision_ref.c

# the portable part of the boot stub (boot/gl_boot_logic.c): in the host
# library for tests/test_boot.c and tools/boot_check.c; on the target it is
# a program of its own (`make boot-cross`), never part of the application
BOOT_SRC := boot/gl_boot_logic.c

FW_SRC   := $(CORE_SRC) $(DRV_SRC) $(APP_LIB_SRC) $(BOOT_SRC)
AUX_SRC  := $(HOSTHAL_SRC) $(SYNTH_SRC) $(SOLVERT_SRC) $(VISREF_SRC)

# ---- host flavours (selected by the recursive invocations below) ----------
BUILD    ?= build/host
SAN      ?=
HOSTOPT  ?= -O2 -g
# Extra -D for the tests (the sanitizer build runs fewer reads per scene of
# tests/test_read.c: it is 3-4 times slower).
TESTDEF  ?=
HOSTFLAGS := $(WARN) $(HOSTOPT) $(SAN) $(TESTDEF) $(RELDEF) -fno-common -MMD -MP $(INC)

FW_OBJ   := $(patsubst %.c,$(BUILD)/%.o,$(FW_SRC))
AUX_OBJ  := $(patsubst %.c,$(BUILD)/%.o,$(AUX_SRC))
# the double-precision comparison build of the solver and of its test harness
S64_OBJ  := $(patsubst core/%.c,$(BUILD)/core64/%.o,$(SOLVER_SRC)) \
            $(BUILD)/tests/solver64/gl_solver_run.o \
            $(BUILD)/tests/solver64/gl_solver_ref.o
TEST_BIN := $(patsubst tests/%.c,$(BUILD)/tests/%,$(TEST_SRC))
LIB      := $(BUILD)/libgl.a

.PHONY: all test asan cross cross-hal config config-check clean run-tests diff bench appdiff \
        bench-vision profile pins pins-check boot-cross release-gate tooltest replay-demo glsim \
        steep-sweep readme-logs readme-check
.SECONDARY:
all: test

test: config-check
	@echo "$(HOSTCC) $(WARN) -O2   (+ $(FW_WARN) for core, drivers, app)"
	@$(MAKE) --no-print-directory run-tests BUILD=build/host SAN=

# float-cast-overflow is not part of "undefined" in gcc; it is added because
# the vision code converts many computed floats to pixel indices.
asan: config-check
	@echo "$(HOSTCC) $(WARN) -O1 -fsanitize=address,undefined,float-cast-overflow"
	@$(MAKE) --no-print-directory run-tests BUILD=build/asan HOSTOPT="-O1 -g" \
	  TESTDEF="-DGL_READ_TEST_TRIALS=3" \
	  SAN="-fsanitize=address,undefined,float-cast-overflow -fno-sanitize-recover=all -fno-omit-frame-pointer"

$(BUILD)/core/%.o: core/%.c
	@mkdir -p $(dir $@)
	@echo "  CC      $<"
	$(Q)$(HOSTCC) $(HOSTFLAGS) $(FW_WARN) -c $< -o $@
$(BUILD)/core64/%.o: core/%.c
	@mkdir -p $(dir $@)
	@echo "  CC      $< (double)"
	$(Q)$(HOSTCC) $(HOSTFLAGS) $(FW_WARN) -DGL_SOLVER_DOUBLE -c $< -o $@
$(BUILD)/drivers/%.o: drivers/%.c
	@mkdir -p $(dir $@)
	@echo "  CC      $<"
	$(Q)$(HOSTCC) $(HOSTFLAGS) $(FW_WARN) -c $< -o $@
$(BUILD)/app/%.o: app/%.c
	@mkdir -p $(dir $@)
	@echo "  CC      $<"
	$(Q)$(HOSTCC) $(HOSTFLAGS) $(FW_WARN) -c $< -o $@
$(BUILD)/boot/%.o: boot/%.c
	@mkdir -p $(dir $@)
	@echo "  CC      $<"
	$(Q)$(HOSTCC) $(HOSTFLAGS) $(FW_WARN) -c $< -o $@
$(BUILD)/hal/host/%.o: hal/host/%.c
	@mkdir -p $(dir $@)
	@echo "  CC      $<"
	$(Q)$(HOSTCC) $(HOSTFLAGS) -c $< -o $@
$(BUILD)/tests/synth/%.o: tests/synth/%.c
	@mkdir -p $(dir $@)
	@echo "  CC      $<"
	$(Q)$(HOSTCC) $(HOSTFLAGS) -c $< -o $@
$(BUILD)/tests/solver/%.o: tests/solver/%.c
	@mkdir -p $(dir $@)
	@echo "  CC      $<"
	$(Q)$(HOSTCC) $(HOSTFLAGS) -c $< -o $@
$(BUILD)/tests/solver64/%.o: tests/solver/%.c
	@mkdir -p $(dir $@)
	@echo "  CC      $< (double)"
	$(Q)$(HOSTCC) $(HOSTFLAGS) -DGL_SOLVER_DOUBLE -c $< -o $@
$(BUILD)/tests/%.o: tests/%.c
	@mkdir -p $(dir $@)
	@echo "  CC      $<"
	$(Q)$(HOSTCC) $(HOSTFLAGS) -c $< -o $@

$(LIB): $(FW_OBJ) $(AUX_OBJ) $(S64_OBJ)
	@rm -f $@
	@echo "  AR      $@"
	$(Q)ar rcs $@ $^

$(BUILD)/tests/test_%: $(BUILD)/tests/test_%.o $(LIB)
	@echo "  LINK    $@"
	$(Q)$(HOSTCC) $(HOSTFLAGS) $< $(LIB) -lm -o $@

# Run every test executable; report all of them, fail if any failed.
run-tests: $(TEST_BIN)
	@fail=0; n=0; \
	for t in $(TEST_BIN); do \
	  n=$$((n+1)); echo "== $$t"; \
	  ./$$t || { fail=$$((fail+1)); echo "!! $$t exited non-zero"; }; \
	done; \
	echo "== $(BUILD): $$n test executables, $$fail failed"; \
	test $$fail -eq 0

# ---- cross build -----------------------------------------------------------
XBUILD     := build/cross
CROSS_CC   := $(CROSS)gcc
CROSS_FLAGS := $(WARN) $(FW_WARN) -mcpu=cortex-m33 -mthumb -mfpu=fpv5-sp-d16 \
               -mfloat-abi=hard -Os -ffunction-sections -fdata-sections \
               -fstack-usage -fno-common -MMD -MP $(RELDEF) -Icore -Idrivers -Ihal -Iapp
XSRC       := $(CORE_SRC) $(DRV_SRC) $(APP_SRC)
XOBJ       := $(patsubst %.c,$(XBUILD)/%.o,$(XSRC))

$(XBUILD)/%.o: %.c
	@mkdir -p $(dir $@)
	@echo "  XCC     $<"
	$(Q)$(CROSS_CC) $(CROSS_FLAGS) -c $< -o $@

cross: config-check $(XOBJ)
	@echo "$(CROSS_CC) $(CROSS_FLAGS)"
	@PYTHON="$(PYTHON)" sh tools/cross_report.sh "$(CROSS)" $(XOBJ)
	@echo "== RAM: the application object and its large parts (ARM sizeof, bytes; tools/cross_sizes.c)"
	$(Q)$(CROSS_CC) $(filter-out -MMD -MP -fstack-usage,$(CROSS_FLAGS)) -c tools/cross_sizes.c -o $(XBUILD)/cross_sizes.o
	@$(CROSS)nm -S -t d $(XBUILD)/cross_sizes.o | awk '$$4 ~ /^glsz_/ { sub(/^glsz_/, "", $$4); printf "  %-18s %7d\n", $$4, $$2 + 0 }' | sort -k2,2nr
	@$(MAKE) --no-print-directory boot-cross

# ---- the boot stub (DESIGN_SPEC E34; boot/) ---------------------------------
# A program of its own in page 0 of the flash.  `make boot-cross` (also the
# last step of `make cross`) compiles its portable part with the flags of the
# cross build and prints its size.  With STM32_HEADERS=<dir> (the vendor
# headers of `make cross-hal`) it also compiles the STM32U585 part against
# the DEVICE header and LINKS the stub with boot/gl_boot.ld - no C library,
# no start-up file, no HAL - and fails if it does not fit its 8 kB page, has
# data, or needs a library function.  Linked is not run: there is no
# hardware (README, release gates).
BOOTBUILD  := build/boot
BOOT_FLAGS := $(WARN) $(FW_WARN) -mcpu=cortex-m33 -mthumb -mfpu=fpv5-sp-d16 -mfloat-abi=hard \
              -Os -ffunction-sections -fdata-sections -fstack-usage -fno-common \
              -ffreestanding -DSTM32U585xx $(RELDEF) -Iboot

boot-cross:
	@sh tools/boot_cross.sh "$(STM32_HEADERS)" "$(CROSS)" "$(BOOTBUILD)" "$(BOOT_FLAGS)"

# ---- release gate: the USB ids, the regulatory text ----------------------------
# Exits non-zero while app/gl_usb_ids.h holds the named placeholders.
ifeq ($(RELEASE),1)
# every test and cross target begins with config-check: a release build stops
# here, whatever objects an earlier build has left behind
config-check: release-gate
boot-cross: release-gate
endif

release-gate:
	@mkdir -p build
	@bad=0; \
	if echo '#include "gl_usb_ids.h"' | $(HOSTCC) -DGL_RELEASE_BUILD -Iapp -fsyntax-only -x c - \
	      2>build/release-gate.log; then \
	  echo "release-gate: USB vendor / product ids are assigned"; \
	else \
	  echo "release-gate: REFUSED - the USB vendor and product ids are placeholders"; \
	  echo "  (app/gl_usb_ids.h: GL_USB_VID_PLACEHOLDER / GL_USB_PID_PLACEHOLDER; DESIGN_SPEC E34)"; \
	  sed 's/^/  | /' build/release-gate.log | head -4; bad=1; \
	fi; \
	if echo '#include "gl_regulatory.h"' | $(HOSTCC) -DGL_RELEASE_BUILD -Iapp -fsyntax-only -x c - \
	      2>build/release-gate-text.log; then \
	  echo "release-gate: the regulatory text of the INFO screen is supplied"; \
	else \
	  echo "release-gate: REFUSED - the regulatory text of the INFO screen is the placeholder"; \
	  echo "  (app/gl_regulatory.h: GL_REGULATORY_TEXT_IS_PLACEHOLDER; the text comes from docs/COMPLIANCE.md)"; \
	  sed 's/^/  | /' build/release-gate-text.log | head -4; bad=1; \
	fi; \
	test $$bad -eq 0

# ---- the STM32 backend against the vendor's headers (compile only) ---------
# hal/stm32u5/gl_hal_stm32u5.c is written against ST's STM32U5 HAL.  No vendor
# file is part of this repository.  `make cross-hal STM32_HEADERS=<dir>`
# compiles the backend - COMPILE ONLY: no HAL sources, no start-up code, no
# linker script, nothing linked or run - against header files that a person
# has put into <dir>, laid out as the three public repositories are:
#   <dir>/cmsis_device_u5/Include/      stm32u5xx.h stm32u585xx.h system_stm32u5xx.h
#   <dir>/stm32u5xx_hal_driver/Inc/     stm32u5xx_hal*.h stm32u5xx_ll_*.h Legacy/
#   <dir>/CMSIS_5/CMSIS/Core/Include/   core_cm33.h cmsis_*.h mpu_armv8.h
# (README, "STM32 backend": the files and release tags it was last compiled
# against).  The headers are data: nothing in <dir> is executed, and nothing
# from it is copied into this tree.  The project's own HAL configuration is
# hal/stm32u5/stm32u5xx_hal_conf.h.  Without STM32_HEADERS, or if the headers
# are not there, the target is SKIPPED with a message and succeeds.
# hal/stm32u5/gl_hal_stm32u5_usb.c is not compiled: it also needs ST's USB
# device library (usbd_core.h, usbd_cdc.h), which is in none of the three.
STM32_HEADERS ?=
HALBUILD   := build/cross-hal
HAL_SRC    := hal/stm32u5/gl_hal_stm32u5.c
HAL_OBJ    := $(patsubst hal/stm32u5/%.c,$(HALBUILD)/%.o,$(HAL_SRC))
HAL_NEED   := cmsis_device_u5/Include/stm32u585xx.h stm32u5xx_hal_driver/Inc/stm32u5xx_hal.h \
              CMSIS_5/CMSIS/Core/Include/core_cm33.h
HAL_FLAGS  := $(WARN) $(FW_WARN) -mcpu=cortex-m33 -mthumb -mfpu=fpv5-sp-d16 \
              -mfloat-abi=hard -Os -ffunction-sections -fdata-sections \
              -fstack-usage -fno-common -DSTM32U585xx -DUSE_HAL_DRIVER $(RELDEF) \
              -Icore -Idrivers -Ihal -Ihal/stm32u5 -Iapp -Iboot

cross-hal: config-check
	@sh tools/cross_hal.sh "$(STM32_HEADERS)" "$(CROSS)" "$(HALBUILD)" "$(HAL_FLAGS)" \
	    "$(HAL_NEED)" $(HAL_SRC)

# ---- generated sources -----------------------------------------------------
VECTORS_JSON := ../sim/results/reference_vectors.json

# The pin map of the board: exported by the netlist (electrical/gl1_main/
# check_pinmap.py), the ONLY input of tools/gen_pins.py.
PINMAP := ../electrical/gl1_main/pinmap.json
PINS_H := hal/stm32u5/gl_pins.h

config: pins
	$(PYTHON) tools/gen_config.py ../design/master_params.yaml core/gl_config.h
	$(PYTHON) tools/gen_font.py core/gl_font_data.c
	$(PYTHON) tools/gen_vectors.py $(VECTORS_JSON) tests/solver/gl_solver_vectors.c

pins:
	$(PYTHON) tools/gen_pins.py $(PINMAP) $(PINS_H)

# Stale header, or a generator that has stopped refusing bad pin maps: both
# fail.  Needs python3 only (no PyYAML).
pins-check:
	@$(PYTHON) tools/gen_pins.py --check $(PINMAP) $(PINS_H)
	@$(PYTHON) tools/gen_pins.py --selftest $(PINMAP)

# Fails if the checked-in generated files are stale.  The part that needs
# PyYAML is skipped (with a note) when it is not installed: the generated
# files are checked in.  The pin map is checked whenever python3 is there.
config-check:
	@if $(PYTHON) -c "import json" 2>/dev/null; then \
	  $(MAKE) --no-print-directory pins-check; \
	else echo "pins-check skipped (python3 not available)"; fi
	@if $(PYTHON) -c "import yaml" 2>/dev/null; then \
	  $(PYTHON) tools/gen_config.py --check ../design/master_params.yaml core/gl_config.h && \
	  $(PYTHON) tools/gen_font.py --check core/gl_font_data.c && \
	  $(PYTHON) tools/gen_vectors.py --check $(VECTORS_JSON) tests/solver/gl_solver_vectors.c; \
	else echo "config-check skipped (python3 + PyYAML not available)"; fi

# ---- differential test against the Python reference (not part of `make test`) --
DIFFDIR  := build/diff
DIFF_N   ?= 20000
DIFF_CFLAGS := $(WARN) $(FW_WARN) -O2 -g -fPIC -Icore

$(DIFFDIR)/libglsolver64.so: $(SOLVER_SRC) tools/diff_solver_abi.c $(wildcard core/gl_solver*.h)
	@mkdir -p $(dir $@)
	@echo "  SO      $@ (double)"
	$(Q)$(HOSTCC) $(DIFF_CFLAGS) -DGL_SOLVER_DOUBLE -shared $(SOLVER_SRC) tools/diff_solver_abi.c -lm -o $@
$(DIFFDIR)/libglsolver32.so: $(SOLVER_SRC) tools/diff_solver_abi.c $(wildcard core/gl_solver*.h)
	@mkdir -p $(dir $@)
	@echo "  SO      $@ (single)"
	$(Q)$(HOSTCC) $(DIFF_CFLAGS) -shared $(SOLVER_SRC) tools/diff_solver_abi.c -lm -o $@

# ---- how much work one estimate costs (host; see tools/solver_bench.c) ----------
bench: config-check
	@$(MAKE) --no-print-directory build/host/libgl.a BUILD=build/host SAN=
	$(Q)$(HOSTCC) $(WARN) -O2 -g $(INC) tools/solver_bench.c build/host/libgl.a -lm -o build/host/solver_bench
	@./build/host/solver_bench all

# ---- how much work the camera part of a read costs (host) ------------------------
# bench-vision: one read of each scene of tools/vision_bench.c on the simulator
#   and what the cost table hal/host/gl_sim_cost.h charges for it.
# profile: the same under valgrind's callgrind (needs valgrind): the MEASURED
#   instruction counts of every stage, against the cost table.
build/host/vision_bench: tools/vision_bench.c config-check
	@$(MAKE) --no-print-directory build/host/libgl.a BUILD=build/host SAN=
	$(Q)$(HOSTCC) $(WARN) -O2 -g $(INC) tools/vision_bench.c build/host/libgl.a -lm -o $@

bench-vision: build/host/vision_bench
	@./build/host/vision_bench all

profile: build/host/vision_bench
	@$(MAKE) --no-print-directory build/host/tests/test_read BUILD=build/host SAN=
	$(Q)$(HOSTCC) $(WARN) -O2 -g $(INC) tools/solver_bench.c build/host/libgl.a -lm -o build/host/solver_bench
	@sh tools/vision_cost.sh build/host build/profile

diff: $(DIFFDIR)/libglsolver64.so $(DIFFDIR)/libglsolver32.so
	$(PYTHON) tools/diff_solver.py --lib $(DIFFDIR)/libglsolver64.so --vectors --random $(DIFF_N)
	$(PYTHON) tools/diff_solver.py --lib $(DIFFDIR)/libglsolver32.so --single --vectors --random $(DIFF_N)

# ---- DESIGN_SPEC E31: the sweep the "TOO STEEP" threshold was chosen from ------
# tools/steep_sweep.py: how often the aim flips on a one-microradian change of
# the tilt, by the steepness ratio core/gl_ui.c computes - with the Python
# reference and with the firmware's single-precision solver (needs the
# reference's Python environment, like `make diff`; about 8 minutes).
STEEP_REF ?= 20000
STEEP_FW  ?= 100000
STEEP_THR := $(shell sed -n 's/^.define GL_UI_STEEP_RATIO \([0-9.]*\)f.*/\1/p' core/gl_ui.h)
steep-sweep: $(DIFFDIR)/libglsolver32.so
	$(PYTHON) tools/steep_sweep.py --lib $(DIFFDIR)/libglsolver32.so --ref $(STEEP_REF) --fw $(STEEP_FW) \
	    --threshold $(STEEP_THR)

# ---- application-level differential check (not part of `make test`) -----------
# tests/test_e2e_putt.c runs the whole firmware on the simulator and dumps every
# estimator call the application made; tools/app_diff.py runs the Python
# reference on the same records and compares (needs the reference's Python
# environment, like `make diff`).
APPDIFF_REC := build/appdiff/app_records.jsonl

appdiff: config-check
	@$(MAKE) --no-print-directory build/host/tests/test_e2e_putt BUILD=build/host SAN=
	@mkdir -p $(dir $(APPDIFF_REC))
	./build/host/tests/test_e2e_putt $(APPDIFF_REC) > build/appdiff/test_e2e_putt.log
	$(PYTHON) tools/app_diff.py $(APPDIFF_REC)

# ---- the PC tool against the host simulator (not part of `make test`) ---------
# build/host/glsim is the whole firmware on the simulated board with its USB
# port on stdin / stdout (tools/glsim_host.c); tools/glctl --sim talks to it.
# `make tooltest` runs tools/glctl/selftest.py: every protocol command through
# glctl against that program, the log download with resume, the decoder
# against the firmware's own values, the REPLAY of the logged reads through
# the Python reference (needs the reference's environment: numpy, scipy), the
# image stamping tool against the boot stub's own check, and the release gate.
# `make replay-demo` is the replay part alone.
build/host/glsim: tools/glsim_host.c config-check
	@$(MAKE) --no-print-directory build/host/libgl.a BUILD=build/host SAN=
	$(Q)$(HOSTCC) $(WARN) -O2 -g $(INC) tools/glsim_host.c build/host/libgl.a -lm -o $@
build/host/boot_check: tools/boot_check.c boot/gl_boot_logic.c boot/gl_boot.h
	@mkdir -p build/host
	$(Q)$(HOSTCC) $(WARN) -O2 -g -Iboot tools/boot_check.c boot/gl_boot_logic.c -o $@

glsim: build/host/glsim

tooltest: build/host/glsim build/host/boot_check
	$(PYTHON) tools/glctl/selftest.py --glsim build/host/glsim --boot-check build/host/boot_check \
	    --out build/tooltest --make "$(MAKE)"

replay-demo: build/host/glsim
	$(PYTHON) tools/glctl/selftest.py --glsim build/host/glsim --out build/tooltest --replay-only

# ---- the README's figures against the runs ------------------------------------
# `make readme-logs` runs the targets whose output the README quotes and keeps
# each output in build/readme/<target>.log (about half an hour - 28 minutes in
# the rev E run: test 7, asan 9, diff 3, steep-sweep 9; every step must
# succeed).  With STM32_HEADERS set it
# also keeps cross-hal and boot-cross.  `make readme-check` then runs
# tools/readme_check.py: every block of README.md between
#     <!-- readme-check:begin NAME -->  and  <!-- readme-check:end NAME -->
# must be, character for character, what the script generates from those logs,
# and every single figure the script binds (its CHECKS table) must be in the
# README as the logs have it.  `python3 tools/readme_check.py --update`
# rewrites the blocks; the prose around them is a person's.
RDLOG := build/readme
readme-logs:
	@mkdir -p $(RDLOG)
	@for t in test cross appdiff tooltest replay-demo bench-vision bench diff steep-sweep asan; do \
	  echo "== readme-logs: make $$t"; \
	  $(MAKE) --no-print-directory $$t > $(RDLOG)/$$t.log 2>&1 || { echo "!! make $$t failed: $(RDLOG)/$$t.log"; exit 1; }; \
	  tail -1 $(RDLOG)/$$t.log; \
	done
	@if [ -n "$(STM32_HEADERS)" ]; then \
	  for t in cross-hal boot-cross; do \
	    echo "== readme-logs: make $$t"; \
	    $(MAKE) --no-print-directory $$t STM32_HEADERS="$(STM32_HEADERS)" > $(RDLOG)/$$t.log 2>&1 || exit 1; \
	    tail -1 $(RDLOG)/$$t.log; \
	  done; \
	fi
	@date -u '+logs complete %Y-%m-%d %H:%M UTC' > $(RDLOG)/stamp.txt; cat $(RDLOG)/stamp.txt

readme-check:
	@$(PYTHON) tools/readme_check.py --logs $(RDLOG) --readme README.md

clean:
	rm -rf build

-include $(shell test -d build && find build -name '*.d' 2>/dev/null)
