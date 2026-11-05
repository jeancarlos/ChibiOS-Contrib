#!/usr/bin/env python3
"""Exercise SN32 SPI abort with an emulated receive FIFO."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[3]
source = (root / 'os/hal/ports/SN32/LLD/SN32F2xx/SPI/hal_spi_v2_lld.c').read_text()
start = source.index('msg_t spi_lld_stop_transfer(')
end = source.index('\n/*', start)
function = source[start:end]
prefix = r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
using msg_t = int;
#define HAL_RET_SUCCESS 0
struct Registers;
struct Empty {
    Registers *regs;
    operator bool() const;
};
struct Data {
    Registers *regs;
    operator uint16_t();
};
struct Registers {
    uint8_t fifo[8] = {};
    size_t head = 0, length = 0;
    struct { Empty RX_EMPTY; } STAT_b;
    Data DATA;
    Registers() : STAT_b{{this}}, DATA{this} {}
};
Empty::operator bool() const { return regs->head == regs->length; }
Data::operator uint16_t() { assert(regs->head < regs->length); return regs->fifo[regs->head++]; }
struct SPIDriver { Registers *spi; uint8_t *rxbuf; size_t count, idx; };
static void reset_fifo(SPIDriver *spip) { spip->spi->head = spip->spi->length; }
#define SPI_FIFO_FRESET(spip) reset_fifo(spip)
'''
suffix = r'''
int main() {
    Registers regs;
    regs.fifo[0] = 0x51;
    regs.fifo[1] = 0x76;
    regs.length = 2;
    uint8_t rx[] = {0xb6, 0, 0, 0xee};
    SPIDriver driver{&regs, rx, 3, 1};
    size_t remaining = 99;
    assert(spi_lld_stop_transfer(&driver, &remaining) == HAL_RET_SUCCESS);
    assert(rx[1] == 0x51 && rx[2] == 0x76);
    assert(rx[3] == 0xee && remaining == 0);
    assert(regs.head == regs.length);

    Registers excess;
    excess.fifo[0] = 0x12;
    excess.fifo[1] = 0x34;
    excess.length = 2;
    uint8_t bounded[] = {0, 0xee};
    SPIDriver short_receive{&excess, bounded, 1, 0};
    (void)spi_lld_stop_transfer(&short_receive, nullptr);
    assert(bounded[0] == 0x12 && bounded[1] == 0xee);

    Registers idle;
    uint8_t empty_buffer[2] = {};
    SPIDriver no_data{&idle, empty_buffer, 2, 0};
    remaining = 99;
    assert(spi_lld_stop_transfer(&no_data, &remaining) == HAL_RET_SUCCESS);
    assert(remaining == 2);

    Registers send_only;
    send_only.fifo[0] = 0x55;
    send_only.length = 1;
    SPIDriver no_receive{&send_only, nullptr, 2, 0};
    remaining = 99;
    assert(spi_lld_stop_transfer(&no_receive, &remaining) == HAL_RET_SUCCESS);
    assert(remaining == 2);
    return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.cpp').write_text(prefix + function + suffix)
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(path / 'test.cpp'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
