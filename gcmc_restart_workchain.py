#!/usr/bin/python
# -*- coding: utf-8 -*-
__author__ = 'Kevin M. Jablonka'
__copyright__ = 'MIT License'
__maintainer__ = 'Kevin M. Jablonka'
__email__ = 'kevin.jablonka@epfl.ch'
__version__ = '0.1.0'
__status__ = 'Dev'

from aiida.orm import CalculationFactory, DataFactory
from aiida.orm.code import Code
from aiida.orm.data.base import Float
from aiida.work import workfunction as wf
from aiida.work.run import submit
from aiida.work.workchain import WorkChain, ToContext, while_, Outputs
from copy import deepcopy
from aiida_raspa.workflows import RaspaConvergeWorkChain

ZeoppCalculation = CalculationFactory('zeopp.network')

# data objects
ArrayData = DataFactory('array')
CifData = DataFactory('cif')
NetworkParameters = DataFactory('zeopp.parameters')
ParameterData = DataFactory('parameter')
RemoteData = DataFactory('remote')
StructureData = DataFactory('structure')


@wf
def get_zeopp_block_parameters(probe_radius):
    """Create NetworkParameters from probe radius.
    :param sigma: Probe radius (A)
    """
    sigma = probe_radius.value

    params = {
        'ha': True,
        'block': [sigma, 100],
    }

    return NetworkParameters(dict=params)

class ResubmitGCMC(WorkChain):
    @classmethod
    def define(cls, spec):
        super(ResubmitGCMC, cls).define(spec)

        # structure, adsorbant, pressures
        spec.input('structure', valid_type=CifData)
        spec.input("probe_radius", valid_type=Float)
        spec.input("pressure", valid_type=ArrayData)

        # zeopp
        spec.input('zeopp_code', valid_type=Code)
        spec.input("_zeopp_options", valid_type=dict, default=None, required=False)

        # raspa
        spec.input("raspa_code", valid_type=Code)
        spec.input("raspa_parameters", valid_type=ParameterData)
        spec.input("_raspa_options", valid_type=dict, default=None, required=False)

        # settings
        spec.input("_usecharges", valid_type=bool, default=True, required=False)

        # workflow
        spec.outline(
            cls.init,  # read pressures, switch on cif charges if _usecharges=True
            cls.run_block_zeopp,  # computes sa, vol, povol, res, e chan, block pockets
            cls.init_raspa_calc,  # assign HeliumVoidFraction=POAV and UnitCells
            while_(cls.should_run_loading_raspa)(
                cls.run_loading_raspa,  # for each P, recover the last snapshoot of the previous and run GCMC
                cls.parse_loading_raspa,
            ),
            cls.return_results,
        )

        spec.dynamic_output()