import json
import random

# Paraphrased notes for different directives
NOTES_POOL = {
    "solar_reduction": [
        ("Solar output will drop to about 20% from {start} to {end}.", 0.2),
        ("Panel washing from {start} until {end} will leave roughly 10% of normal solar output.", 0.1),
        ("Expect an 80% reduction in rooftop solar during the {start}-{end} maintenance window.", 0.2),
        ("Solar power available will be halved between {start} and {end} due to heavy cloud cover.", 0.5)
    ],
    "minimum_battery_reserve": [
        ("Keep at least {val} kWh in reserve from {start} until {end}.", None),
        ("Maintain a minimum battery charge of {val} kWh between {start} and {end}.", None),
        ("Battery must not drop below {val} kWh during the hours of {start} to {end}.", None)
    ],
    "no_charge_window": [
        ("Do not charge the battery between {start} and {end}.", None),
        ("Grid charging is disabled from {start} to {end}.", None),
        ("Battery charging systems will be offline between {start} and {end}.", None)
    ],
    "no_discharge_window": [
        ("Discharging from battery is prohibited from {start} to {end}.", None),
        ("Keep battery discharging disabled between {start} and {end}.", None),
        ("Do not draw power from the battery between {start} and {end}.", None)
    ],
    "max_grid_window": [
        ("Grid usage cannot exceed {val} kWh from {start} to {end}.", None),
        ("Limit grid import to a maximum of {val} kWh between {start} and {end}.", None),
        ("Grid capacity is capped at {val} kWh during {start} to {end}.", None)
    ],
    "no_op": [
        ("The cafeteria menu changes tomorrow.", None),
        ("Reminder: the staff meeting is at 2 PM.", None),
        ("It will be a sunny day today overall.", None),
        ("Ignore this note.", None)
    ]
}

def generate_cases():
    cases = []
    for i in range(100):
        # 1. Generate battery
        capacity = random.choice([200.0, 500.0, 1000.0])
        initial = round(random.uniform(20, capacity), 2)
        min_energy = round(random.uniform(0, initial - 10), 2)
        max_charge = round(random.uniform(50, 200), 2)
        max_discharge = round(random.uniform(50, 200), 2)

        battery = {
            "capacity_kwh": capacity,
            "initial_energy_kwh": initial,
            "minimum_energy_kwh": min_energy,
            "max_charge_kwh_per_hour": max_charge,
            "max_discharge_kwh_per_hour": max_discharge
        }

        # 2. Generate hours
        hours = []
        for h in range(24):
            # Demand ranges from 10 to 100
            demand = round(random.uniform(10.0, 100.0), 2)
            # Solar is positive only between hour 6 and 18
            solar = 0.0
            if 6 <= h <= 18:
                solar = round(random.uniform(0, 80.0), 2)
            
            # Tariff varies between 5 and 15
            tariff = round(random.uniform(5.0, 15.0), 2)

            hours.append({
                "hour": h,
                "demand_kwh": demand,
                "solar_kwh": solar,
                "tariff_bdt_per_kwh": tariff
            })

        # 3. Generate operator notes
        num_notes = random.randint(1, 3)
        chosen_directives = random.sample(list(NOTES_POOL.keys()), num_notes)
        
        operator_notes = []
        for d_type in chosen_directives:
            template, factor_val = random.choice(NOTES_POOL[d_type])
            start_h = random.randint(0, 20)
            end_h = random.randint(start_h + 1, 23)

            # Some directives need a value
            val = None
            if d_type == "minimum_battery_reserve":
                val = round(random.uniform(min_energy + 10, capacity - 10), 1)
            elif d_type == "max_grid_window":
                val = round(random.uniform(20.0, 150.0), 1)
            
            note_str = template.replace("{start}", f"{start_h}:00").replace("{end}", f"{end_h}:00")
            if val is not None:
                note_str = note_str.replace("{val}", str(val))
            
            operator_notes.append(note_str)

        scenario_id = f"HIDDEN-{i:03d}"
        cases.append({
            "scenario_id": scenario_id,
            "operator_notes": operator_notes,
            "hours": hours,
            "battery": battery
        })

    with open("100_hidden_cases.json", "w") as f:
        json.dump(cases, f, indent=2)

    print("Generated 100 cases to 100_hidden_cases.json")

if __name__ == "__main__":
    generate_cases()
