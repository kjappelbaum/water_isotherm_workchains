#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test RDF and density of bulk water in box for different water models to validate
FF definition and AiiDA installation.
"""

from __future__ import print_function
from __future__ import absolute_import
import os
import sys
import click

from aiida.common import NotExistent
from aiida.engine import run_get_pk, run, submit
from aiida.orm import Code, Dict
from aiida.plugins import DataFactory
from aiida_raspa.calculations import RaspaCalculation

# data objects
CifData = DataFactory("cif")  # pylint: disable=invalid-name

forcefields = [
    ("UFF-OPC-TC", "opc"),
    ("UFF-OPC3-TC", "opc3"),
    ("UFF-SPC-TC", "spc"),
    ("UFF-SPCE-TC", "spce"),
    ("UFF-ST2-TC", "st2"),
    ("UFF-TIP3P-TC", "tip3p"),
    ("UFF-TIP4P-2005-TC", "tip4p2005"),
    ("UFF-TIP4P-Ew", "tip4p-ew"),
    ("UFF-TIP5P-TC", "tip5p"),
    ("UFF-TIP7P-TC", "tip7p")
]

@click.command("cli")
@click.argument("codelabel")
@click.option("--submit", is_flag=True, help="Actually submit calculation")
def main(codelabel, submit):
    """Prepare and submit RASPA calculation."""
    try:
        code = Code.get_from_string(codelabel)
    except NotExistent:
        print("The code '{}' does not exist".format(codelabel))
        sys.exit(1)

    # parameters
    parameters = Dict(
        dict={
            "GeneralSettings": {
                "SimulationType": "MonteCarlo",
                "NumberOfCycles": 250000,
                "NumberOfInitializationCycles": 50000,
                "PrintEvery": 10000,
                "Forcefield": "UFF-SPC-TC",
                "EwaldPrecision": 1e-6,
                "WriteBinaryRestartFileEvery": 20000,
                "CutOff": 10, # in the fitting procedures commonly truncated around 9 A
            },
            "System": {
                "box_25_angstroms": {
                    "type": "Box",
                    "BoxLengths": "24.83 24.83 24.83",
                    "ExternalTemperature": 298.0,
                    "ExternalPressure":  101325.01, # 1 atm
                    "ComputeRDF": "yes",
                    "WriteRDFEvery": 50000,
                    "VolumeChangeProbability":  0.05, # NPT to compute the density
                }
            },
            "Component": {
                "spc": {
                    "MoleculeDefinition": "spc",
                    "TranslationProbability": 0.5,
                    "RotationProbability": 0.5,
                    "ReinsertionProbability": 1.0,
                    "CreateNumberOfMolecules": {"box_25_angstroms": 512},
                }
            },
        }
    )

    # resources
    options = {
        "resources": {"num_machines": 1, "num_mpiprocs_per_machine": 1},
        "max_wallclock_seconds": 72 * 60 * 60,  # 30 min
        "withmpi": False,
    }

    settings = Dict(dict={"additional_retrieve_list": ["RadialDistributionFunctions/System_0/*"]})

    # collecting all the inputs
    inputs = {
        "parameters": parameters,
        "code": code,
        "settings": settings,
        "metadata": {"options": options, "dry_run": False, "store_provenance": True},
    }

    if submit:
        submit(RaspaCalculation, **inputs)
        print("calculation pk: ", pk)
    else:
        print("Generating test input ...")
        inputs["metadata"]["dry_run"] = True
        inputs["metadata"]["store_provenance"] = False
        run(RaspaCalculation, **inputs)
        print("Submission test successful")
        print("In order to actually submit, add '--submit'")


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
