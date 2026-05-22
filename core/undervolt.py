from core.msr import _read_msr, _write_msr, MSR_VOLTAGE, _get_cpus, _sudo_hw, _sudo_hw_read

PLANES = {
    'core': 0, 'gpu': 1, 'cache': 2, 'uncore': 3, 'analogio': 4
}

PLANE_NAMES = {
    0: 'core',
    1: 'gpu',
    2: 'cache',
    3: 'uncore',
    4: 'analogio'
}

def _mv_to_offset(mv: float) -> int:
    # 1/1024V units, 11-bit two's complement
    mv = max(-300.0, min(0.0, mv))
    return int(round(mv * 1.024)) & 0x7FF

def _offset_to_mv(raw: int) -> float:
    # Extract bits [31:21] from the 64-bit response
    field = (raw >> 21) & 0x7FF
    if field & 0x400: # Sign bit
        field -= 0x800
    return round(field / 1.024, 2)

def set_undervolt(plane: str, offset_mv: float) -> bool:
    if plane not in PLANES: return False
    plane_idx = PLANES[plane]
    offset = _mv_to_offset(offset_mv)
    
    # Mailbox Write (bit 63 = 1)
    # Command 0x11 = Write
    val = (1 << 63) | (plane_idx << 40) | (0x11 << 32) | (offset << 21)
    
    success = True
    for cpu in _get_cpus() or [0]:
        if not _write_msr(val, cpu, MSR_VOLTAGE):
            success = False
    return success

def get_undervolt(plane: str) -> float:
    if plane not in PLANES: return 0.0
    plane_idx = PLANES[plane]
    
    # Mailbox Read Request (bit 63 = 1, Command 0x10)
    # This triggers the CPU to put the current offset of the plane into MSR 0x150
    read_req = (1 << 63) | (plane_idx << 40) | (0x10 << 32)
    
    cpu = 0
    cpus = _get_cpus()
    if cpus: cpu = cpus[0]
    
    # Write request then read response
    if _write_msr(read_req, cpu, MSR_VOLTAGE):
        res = _read_msr(cpu, MSR_VOLTAGE)
        if res is not None:
            return _offset_to_mv(res)
    
    return 0.0

def read_undervolt() -> dict[str, float]:
    """Read all voltage offsets from MSR."""
    # Ensure MSR is loaded
    from core.msr import _load_msr
    _load_msr()
    
    return {plane: get_undervolt(plane) for plane in PLANES}
