# GreenLine GL-1 firmware - host tests and cross-compile check.
#
#   make test    build everything for the host with
#                gcc -std=c99 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror
#                and run every tests/test_*.c executable
#   make asan    the same under -fsanitize=address,undefined
#   make cross   compile core/, drivers/ and app/ (NOT hal/stm32u5, NOT hal/host)
#                with arm-none-eabi-gcc for the Cortex-M33 and print the size
#                table, the largest stack frames and the forbidden-symbol check
#   make config  regenerate core/gl_config.h, core/gl_font_data.c,
#                hal/stm32u5/gl_pins.h and tests/solver/gl_solver_vectors.c
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
#   make clean
#
# Layout rules the wildcards rely on:
#   core/*.c      portable core            (no HAL, no stdio)
#   drivers/*.c   device drivers           (include only hal/gl_hal.h + core)
#   app/*.c       main loop and glue       (app/gl_main.c holds main() and is
#                                           left out of the host test library)
#   hal/host/*.c  host simulator backend of hal/gl_hal.h
#   hal/stm32u5/  STM32U585 backend: NOT compiled by any target here (no
#                 vendor SDK); only its generated pin table gl_pins.h is
#                 checked, by tests/test_pins.c
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

WARN     := -std=c99 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror
# Extra checks for firmware code (core, drivers, app): no silent double
# arithmetic, no variable-length arrays, every global function declared.
FW_WARN  := -Wdouble-promotion -Wvla -Wmissing-prototypes -Wstrict-prototypes -Wundef
INC      := -Icore -Idrivers -Ihal -Ihal/host -Ihal/stm32u5 -Iapp -Itests -Itests/synth -Itests/solver \
            -Itests/vision_ref

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

FW_SRC   := $(CORE_SRC) $(DRV_SRC) $(APP_LIB_SRC)
AUX_SRC  := $(HOSTHAL_SRC) $(SYNTH_SRC) $(SOLVERT_SRC) $(VISREF_SRC)

# ---- host flavours (selected by the recursive invocations below) ----------
BUILD    ?= build/host
SAN      ?=
HOSTOPT  ?= -O2 -g
# Extra -D for the tests (the sanitizer build runs fewer reads per scene of
# tests/test_read.c: it is 3-4 times slower).
TESTDEF  ?=
HOSTFLAGS := $(WARN) $(HOSTOPT) $(SAN) $(TESTDEF) -fno-common -MMD -MP $(INC)

FW_OBJ   := $(patsubst %.c,$(BUILD)/%.o,$(FW_SRC))
AUX_OBJ  := $(patsubst %.c,$(BUILD)/%.o,$(AUX_SRC))
# the double-precision comparison build of the solver and of its test harness
S64_OBJ  := $(patsubst core/%.c,$(BUILD)/core64/%.o,$(SOLVER_SRC)) \
            $(BUILD)/tests/solver64/gl_solver_run.o \
            $(BUILD)/tests/solver64/gl_solver_ref.o
TEST_BIN := $(patsubst tests/%.c,$(BUILD)/tests/%,$(TEST_SRC))
LIB      := $(BUILD)/libgl.a

.PHONY: all test asan cross config config-check clean run-tests diff bench appdiff
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
               -fstack-usage -fno-common -MMD -MP -Icore -Idrivers -Ihal -Iapp
XSRC       := $(CORE_SRC) $(DRV_SRC) $(APP_SRC)
XOBJ       := $(patsubst %.c,$(XBUILD)/%.o,$(XSRC))

$(XBUILD)/%.o: %.c
	@mkdir -p $(dir $@)
	@echo "  XCC     $<"
	$(Q)$(CROSS_CC) $(CROSS_FLAGS) -c $< -o $@

cross: config-check $(XOBJ)
	@echo "$(CROSS_CC) $(CROSS_FLAGS)"
	@sh tools/cross_report.sh "$(CROSS)" $(XOBJ)

# ---- generated sources -----------------------------------------------------
VECTORS_JSON := ../sim/results/reference_vectors.json

config:
	$(PYTHON) tools/gen_config.py ../design/master_params.yaml core/gl_config.h
	$(PYTHON) tools/gen_font.py core/gl_font_data.c
	$(PYTHON) tools/gen_pins.py ../design/DESIGN_SPEC.md hal/stm32u5/gl_pins.h
	$(PYTHON) tools/gen_vectors.py $(VECTORS_JSON) tests/solver/gl_solver_vectors.c

# Fails if the checked-in generated files are stale.  Skipped (with a note)
# when python3 or PyYAML is not installed: the generated files are checked in.
config-check:
	@if $(PYTHON) -c "import yaml" 2>/dev/null; then \
	  $(PYTHON) tools/gen_config.py --check ../design/master_params.yaml core/gl_config.h && \
	  $(PYTHON) tools/gen_font.py --check core/gl_font_data.c && \
	  $(PYTHON) tools/gen_pins.py --check ../design/DESIGN_SPEC.md hal/stm32u5/gl_pins.h && \
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

diff: $(DIFFDIR)/libglsolver64.so $(DIFFDIR)/libglsolver32.so
	$(PYTHON) tools/diff_solver.py --lib $(DIFFDIR)/libglsolver64.so --vectors --random $(DIFF_N)
	$(PYTHON) tools/diff_solver.py --lib $(DIFFDIR)/libglsolver32.so --single --vectors --random $(DIFF_N)

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

clean:
	rm -rf build

-include $(shell test -d build && find build -name '*.d' 2>/dev/null)
