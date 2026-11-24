# Minimal RP2350 project for the bundle smoke test. It exercises the Arm GCC toolchain,
# the Pico SDK with TinyUSB (USB stdio), the BTstack files the bundle keeps
# (pico/btstack_flash_bank.h), pioasm (a PIO program) and picotool (UF2 output).
cmake_minimum_required(VERSION 3.13)

if(NOT PICO_SDK_PATH)
    set(PICO_SDK_PATH "$ENV{PICO_SDK_PATH}")
endif()
set(PICO_BOARD pico2)
include("${PICO_SDK_PATH}/external/pico_sdk_import.cmake")

project(blink C CXX ASM)
pico_sdk_init()

add_executable(blink blink.c)
pico_generate_pio_header(blink ${CMAKE_CURRENT_LIST_DIR}/blink.pio)
target_link_libraries(blink pico_stdlib hardware_pio pico_btstack_flash_bank_headers)
pico_enable_stdio_usb(blink 1)
pico_enable_stdio_uart(blink 0)
pico_add_extra_outputs(blink)
