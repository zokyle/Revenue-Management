# GreenLine GL-1 firmware - host tests and cross-compile check.
#
#   make test    build everything for the host with
#                gcc -std=c99 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror
#                and run every tests/test_*.c executable
#   make asan    the same under -fsanitize=address,undefined
#   make cross   compile core/, drivers/ and app/ (NOT hal/stm32u5, NOT hal/host)
#                with arm-none-eabi-gcc for the Cortex-M33 and print the size
#                table, the largest stack frames and the forbidden-symbol check
#   make config  regenerate core/gl_config.h, core/gl_font_data.c and
#                hal/stm32u5/gl_pins.h
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
#   tests/test_*.c   one executable each, each with its own main()

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
INC      := -Icore -Idrivers -Ihal -Ihal/host -Ihal/stm32u5 -Iapp -Itests -Itests/synth

CORE_SRC    := $(sort $(wildcard core/*.c))
DRV_SRC     := $(sort $(wildcard drivers/*.c))
APP_SRC     := $(sort $(wildcard app/*.c))
APP_LIB_SRC := $(filter-out app/gl_main.c,$(APP_SRC))
HOSTHAL_SRC := $(sort $(wildcard hal/host/*.c))
SYNTH_SRC   := $(sort $(wildcard tests/synth/*.c))
TEST_SRC    := $(sort $(wildcard tests/test_*.c))

FW_SRC   := $(CORE_SRC) $(DRV_SRC) $(APP_LIB_SRC)
AUX_SRC  := $(HOSTHAL_SRC) $(SYNTH_SRC)

# ---- host flavours (selected by the recursive invocations below) ----------
BUILD    ?= build/host
SAN      ?=
HOSTOPT  ?= -O2 -g
HOSTFLAGS := $(WARN) $(HOSTOPT) $(SAN) -fno-common -MMD -MP $(INC)

FW_OBJ   := $(patsubst %.c,$(BUILD)/%.o,$(FW_SRC))
AUX_OBJ  := $(patsubst %.c,$(BUILD)/%.o,$(AUX_SRC))
TEST_BIN := $(patsubst tests/%.c,$(BUILD)/tests/%,$(TEST_SRC))
LIB      := $(BUILD)/libgl.a

.PHONY: all test asan cross config config-check clean run-tests
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
	  SAN="-fsanitize=address,undefined,float-cast-overflow -fno-sanitize-recover=all -fno-omit-frame-pointer"

$(BUILD)/core/%.o: core/%.c
	@mkdir -p $(dir $@)
	@echo "  CC      $<"
	$(Q)$(HOSTCC) $(HOSTFLAGS) $(FW_WARN) -c $< -o $@
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
$(BUILD)/tests/%.o: tests/%.c
	@mkdir -p $(dir $@)
	@echo "  CC      $<"
	$(Q)$(HOSTCC) $(HOSTFLAGS) -c $< -o $@

$(LIB): $(FW_OBJ) $(AUX_OBJ)
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
config:
	$(PYTHON) tools/gen_config.py ../design/master_params.yaml core/gl_config.h
	$(PYTHON) tools/gen_font.py core/gl_font_data.c
	$(PYTHON) tools/gen_pins.py ../design/DESIGN_SPEC.md hal/stm32u5/gl_pins.h

# Fails if the checked-in generated files are stale.  Skipped (with a note)
# when python3 or PyYAML is not installed: the generated files are checked in.
config-check:
	@if $(PYTHON) -c "import yaml" 2>/dev/null; then \
	  $(PYTHON) tools/gen_config.py --check ../design/master_params.yaml core/gl_config.h && \
	  $(PYTHON) tools/gen_font.py --check core/gl_font_data.c && \
	  $(PYTHON) tools/gen_pins.py --check ../design/DESIGN_SPEC.md hal/stm32u5/gl_pins.h; \
	else echo "config-check skipped (python3 + PyYAML not available)"; fi

clean:
	rm -rf build

-include $(shell test -d build && find build -name '*.d' 2>/dev/null)
