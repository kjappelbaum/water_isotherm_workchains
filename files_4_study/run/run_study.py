#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import os
import sys
import click
from glob import glob

from aiida.plugins import DataFactory
from aiida.orm import Code, Dict, Float, Int
from aiida.engine import submit
from water_isotherm_workchains.converge_loading_workchain import (
    ConvergeLoadingWorkchain,)
from water_isotherm_workchains.utils.utils import slugify
from six.moves import range

ParameterData = DataFactory('dict')
SinglefileData = DataFactory('singlefile')
CifData = DataFactory('cif')

forcefields = [('DREIDING-UFF-OPC-TC', 'opc'), ('DREIDING-UFF-OPC3-TC', 'opc3'), ('DREIDING-UFF-SPCE-TC', 'spce'),
               ('DREIDING-UFF-ST2-TC', 'st2'), ('DREIDING-UFF-TIP3P-TC', 'tip3p'),
               ('DREIDING-UFF-TIP4P-2005-TC', 'tip4p2005'), ('DREIDING-UFF-TIP4P-Ew-TC', 'tip4p-ew'),
               ('DREIDING-UFF-TIP5P-TC', 'tip5p'), ('DREIDING-UFF-TIP7P-TC', 'tip7p')]

pressures = [
    00.0001e5, 00.001e5, 00.002e5, 00.004e5, 00.006e5, 00.008e5, 00.011e5, 00.014e5, 00.016e5, 00.018e5, 00.021e5,
    00.026e5, 00.03e5, 00.035e5, 00.04e5
]


@click.command('cli')
@click.argument('raspa_code_string')
@click.argument('zeopp_code_string')
def main(raspa_code_string, zeopp_code_string):
    zeopp_code = Code.get_from_string(zeopp_code_string)
    raspa_code = Code.get_from_string(raspa_code_string)
    for s in glob(
            '/home/kevin/Dropbox/Documents/uni/EPFL/master_thesis/water_isotherm_workchains/files_4_study/structures/*.cif'
    ):
        for ff, molecule in forcefields:
            for pressure in pressures:
                structure = CifData(file=s)
                structure_label = slugify(structure.filename)
                structure.label = structure_label

                zeopp_atomic_radii_file = SinglefileData(file=os.path.abspath('../test_files/zeopp.rad'))

                zeopp_options = {
                    'resources': {
                        'num_machines': 1,
                        'tot_num_mpiprocs': 1
                    },
                    'max_memory_kb': 2000000,
                    'max_wallclock_seconds': 2 * 30 * 60,
                    'withmpi': False,
                }

                raspa_options = {
                    'resources': {
                        'num_machines': 1,
                        'tot_num_mpiprocs': 1
                    },
                    'max_memory_kb': 200000,
                    'max_wallclock_seconds': 72 * 60 * 60,
                    'withmpi': False,
                }

                raspa_comp = {
                    'comp1': {
                        'name': molecule,
                        'mol_fraction': 1.0,
                        'mol_def': molecule,
                        'conv_threshold': 3,
                        'radius': 1.325,  # kinetic diameter of water
                        'singlebead': True,  # for rotation probability
                    }
                }

                raspa_parameters = Dict(
                    dict={
                        'GeneralSettings': {
                            'SimulationType': 'MonteCarlo',
                            'NumberOfCycles': 5000,
                            'NumberOfInitializationCycles': 5000,
                            'PrintEvery': 5000,
                            'CutOff': 13.0,
                            'WriteBinaryRestartFileEvery': 5000,
                            'Forcefield': ff,
                            'RemoveAtomNumberCodeFromLabel': True,
                        },
                        'System': {
                            structure_label: {
                                'ExternalTemperature': 298,
                                'ExternalPressure': pressure,
                                'type': 'Framework'
                            }
                        },
                        'Component': {'comp' + str(i + 1): {} for i in range(len(raspa_comp))},
                    })

                zeopp_parameters = Dict(dict={
                    'block_samples': 100,
                    'volpo_samples': 100000,
                    'sa_samples': 100000,
                    'accuracy': 'DEF',
                })

                submit(
                    ConvergeLoadingWorkchain,
                    structure=structure,
                    zeopp_code=zeopp_code,
                    pressure=pressure,
                    min_cycles=Int(50000),
                    zeopp_options=zeopp_options,
                    raspa_options=raspa_options,
                    raspa_parameters=raspa_parameters,
                    zeopp_parameters=zeopp_parameters,
                    raspa_code=raspa_code,
                    raspa_comp=raspa_comp,
                    zeopp_atomic_radii=zeopp_atomic_radii_file,
                    metadata={
                        'label': 'MultiCompIsothermWorkChain-watertest',
                        'description': 'Test for <{}>'.format(structure.label),
                    },
                )


if __name__ == '__main__':
    main()
