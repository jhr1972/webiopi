from sdm_modbus import meter
from sdm_modbus import SDM

class ADL(meter.Meter):
    pass

class ADL400(ADL):

    def __init__(self, *args, **kwargs):
        self.model = "ADL400"
        self.baud = 9600

        super().__init__(*args, **kwargs)

        self.registers = {
            #                    address, length,  rtype,            dtype,                          vtype, label,                     fmt, batch, sf
            "current_total_electricity": (0x016A, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current total electricity", "kWh", 1, 1)
  #          "current_spike_electricity": (0x2, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current spike electric energy", "kWh", 1, 1),
 #           "current_pike_electricity": (0x4, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current peak electric energy", "kWh", 1, 1)
 #           "current_flat_electricity": (0x6, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current flat electric energy", "kWh", 1, 1),
 #           "current_valley_electricity": (0x8, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current valley electric energy", "kWh", 1, 1),
 #           "current_forward_active_total_energy": (0xA, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current forward active total electric energy", "kWh", 1, 1),
 #           "current_forward_active_spike_energy": (0xC, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current forward active spike electric energy", "kWh", 1, 1),
 #           "current_forward_active_peak_energy": (0xE, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current forward active peak electric energy", "kWh", 1, 1),
 #           "current_forward_active_flat_energy": (0x10, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current forward active flat electric energy", "kWh", 1, 1),
 #           "current_forward_active_valley_energy": (0x12, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current forward active valley electric energy", "kWh", 1, 1),
 #           "current_reversing_active_total_energy": (0x14, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current  reversing active total electric energy", "kWh", 1, 1),
 #           "current_reversing_active_spike_electric_energy": (0x16, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current reversing active spike electric energy", "kWh", 1, 1),
 #           "current_reversing_active_peak_electric_energy": (0x18, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current reversing Active peak electric energy", "kWh", 1, 1),
 #           "current_reversing_active_flat_electric_energy": (0x1A, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current  reversing active flat energy", "kWh", 1, 1),
 #           "current_reversing_active_valley_electric_energy": (0x1C, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current reversing active valley energy", "kWh", 1, 1),
 #           "current_total_reactive_electric_energy": (0x1E, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current total reactive electric energy", "kWh", 1, 1),
 #           "current_reversing_active_spike_electric_energy": (0x20, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Current reversing active spike energy", "kWh", 1, 1)
        
#      self.registers = {
#          #                    address, length,  rtype,            dtype,                          vtype, label,                     fmt, batch, sf
#          "l1_power_active": (0x0164, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Active power of A phase", "W", 1, 1),
#          "l2_power_active": (0x0166, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Active power of B phase", "W", 1, 1),
#          "l3_power_active": (0x0168, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Active power of C phase", "W", 1, 1),
#          "power_active": (0x016A, 4, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Active power of C phase", "W", 1, 1)
#          #"l1_power_active": (0x067, 2, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Active power of A phase", "W", 1, 1),
#          #"l2_power_active": (0x0068,2, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Active power of B phase", "W", 1, 1),
            #"l3_power_active": (0x0069,2, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Active power of C phase", "W", 1, 1),
            #"frequency": (0x077, 2, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Frequency", "W", 1, 1)
            
            #"power_active": (0x006A, 2, meter.registerType.HOLDING, meter.registerDataType.FLOAT32, float, "Active power of C phase", "W", 1, 1),

         #   "l2_voltage": (0x0002, 2, meter.registerType.INPUT, meter.registerDataType.FLOAT32, float, "L2 Voltage", "V", 1, 1),
          
        }

