#include <stdio.h>

#include "blink.pio.h"
#include "hardware/pio.h"
#include "pico/btstack_flash_bank.h"
#include "pico/stdlib.h"

int main(void) {
    stdio_init_all();
    uint offset = pio_add_program(pio0, &blink_program);
    pio_sm_config config = blink_program_get_default_config(offset);
    sm_config_set_set_pins(&config, PICO_DEFAULT_LED_PIN, 1);
    pio_gpio_init(pio0, PICO_DEFAULT_LED_PIN);
    pio_sm_set_consecutive_pindirs(pio0, 0, PICO_DEFAULT_LED_PIN, 1, true);
    pio_sm_init(pio0, 0, offset, &config);
    pio_sm_set_enabled(pio0, 0, true);
    for(;;) {
        printf("blink, flash bank at 0x%x\n", (unsigned)PICO_FLASH_BANK_STORAGE_OFFSET);
        sleep_ms(1000);
    }
}
