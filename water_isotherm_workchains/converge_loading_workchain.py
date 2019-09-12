#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import os
import numpy as np
import six
from water_isotherm_workchains.utils.utils import multiply_unit_cell
from copy import deepcopy
from collections import defaultdict
from aiida.common import AttributeDict
from aiida.plugins import CalculationFactory, DataFactory
from aiida.orm import Code, Dict, Float, Int, List, Str, load_node, Bool, Str
from aiida.engine import submit
from aiida.engine import ToContext, WorkChain, workfunction, if_, while_, append_
from six.moves import range

CifData = DataFactory('cif')
ParameterData = DataFactory('dict')
SinglefileData = DataFactory('singlefile')
FolderData = DataFactory('folder')
RaspaCalculation = CalculationFactory('raspa')
ZeoppCalculation = CalculationFactory('zeopp.network')
NetworkParameters = DataFactory('zeopp.parameters')


class ConvergeLoadingWorkchain(WorkChain):
    """
    The ConvergeLoadingWorkchain is designed to resubmit shorter GCMC
    runs until the change is below a desired threshold and the total
    number of cycles is above a desired treshold.

    Philosophy here is to have a lot of short GCMC runs, the current architecture
    assumes that calculation wont't converge in the first simulation.
    This is to be completely sure that one does not run into walltime issues and
    that one also has fine-grained access to the statistics in the results dictionary
    and can perform better averaging. This is to get a compromise between efficiency,
    and being sure that everything is super correct.

    Only the first simulation will have simulation cycles to get to a reasonable
    system configuration. After that, we do not perfom initialization but simply
    restart from the previous configuration.

    Will not reuse block files as the radius for the zeo++ is model dependent,
    at least when using the sigma/2 convention.

    Mutlicomponent code copied from Pezhman Zarabadi-Poor (https://github.com/pzarabadip/aiida-lsmo-workflows/blob/gemc-wc/examples/run_isotherm_1comp_hkust1.py).

    Before performing a GCMC it also runs zeo++ to determine the blocked pockets.
    """

    @classmethod
    def define(cls, spec):
        super(ConvergeLoadingWorkchain, cls).define(spec)

        # structure, adsorbant, pressures
        spec.input('structure', valid_type=CifData)
        spec.input('pressure', valid_type=Float)

        # zeopp
        spec.input('zeopp_code', valid_type=Code)
        spec.input_namespace('zeopp_options', dynamic=True, required=False, non_db=True)
        spec.input('zeopp_atomic_radii', valid_type=SinglefileData, required=False)

        # raspa
        spec.input('raspa_code', valid_type=Code)
        spec.input_namespace('raspa_comp', valid_type=dict, required=False, dynamic=True)

        spec.input('zeopp_parameters', valid_type=ParameterData, required=True)

        spec.input('raspa_parameters', valid_type=ParameterData
                  )  # RASPA input parameters, assumes that system dictionary is already with structure_labels
        spec.input('min_cycles', valid_type=Int, default=Int(10000))  # Minimum number of cycles, before workchain stops
        spec.input('raspa_verbosity', valid_type=Int,
                   default=Int(10))  # will put  PrintEvery to NumCycles divided by this number
        spec.input_namespace('raspa_options', dynamic=True, required=False, non_db=True)  # scheduler options for raspa

        # settings
        spec.input('usecharges', default=Bool(True), required=False, valid_type=Bool)

        # workflow
        spec.outline(
            cls.setup,
            cls.run_zeopp,  # computes volpo and block pockets
            cls.inspect_zeopp_calc,  # extract blocked pockets
            cls.init_raspa_calc,
            cls.run_first_gcmc,  # the first GCMC also runs initialization
            cls.parse_loading_raspa,
            while_(cls.should_run_loading_raspa)(
                cls.run_loading_raspa,  # for each run, recover the last snapshot of the previous and run GCMC
                cls.parse_loading_raspa,
            ),
            cls.return_results,
        )

        # to be returned
        spec.outputs.dynamic = True

    def setup(self):
        """Initialize variables and the pressures we want to compute"""
        self.ctx.structure = self.inputs.structure
        self.ctx.pressure = self.inputs.pressure
        self.ctx.min_cycles = self.inputs.min_cycles

        # Keep track of cyles
        self.ctx.cycles = -1
        self.ctx.counter = -1

        # Set up dictionaries, we want to record the progress of the simulation
        self.ctx.raspa_comp = AttributeDict(self.inputs.raspa_comp)
        self.ctx.loading = defaultdict(list)
        self.ctx.loading_dev = defaultdict(list)
        self.ctx.adsorbate_density_average = defaultdict(list)
        self.ctx.adsorbate_density_dev = defaultdict(list)
        self.ctx.enthalpy_of_adsorption_average = []
        self.ctx.enthalpy_of_adsorption_dev = []

        # Keeping track of total energies
        self.ctx.total_energy_average = []
        self.ctx.total_energy_dev = []

        # Keeping track of host-ads energies
        self.ctx.host_ads_total_energy_average = []
        self.ctx.host_ads_total_energy_dev = []

        self.ctx.host_ads_vdw_energy_average = []
        self.ctx.host_ads_vdw_energy_dev = []

        self.ctx.host_ads_coulomb_energy_average = []
        self.ctx.host_ads_coulomb_energy_dev = []

        # Keeping track of ads-ads energies
        self.ctx.ads_ads_total_energy_average = []
        self.ctx.ads_ads_total_energy_dev = []

        self.ctx.ads_ads_coulomb_energy_average = []
        self.ctx.ads_ads_coulomb_energy_dev = []

        self.ctx.ads_ads_vdw_energy_average = []
        self.ctx.ads_ads_vdw_energy_dev = []

        # Keeping track of adsorption enthapies
        self.ctx.enthalpy_of_adsorption_average = []
        self.ctx.enthalpy_of_adsorption_dev = []

        self.ctx.raspa_parameters = deepcopy(self.inputs.raspa_parameters.get_dict())

        if self.inputs.usecharges:
            self.ctx.raspa_parameters['ChargeMethod'] = 'Ewald'
            self.ctx.raspa_parameters['EwaldPrecision'] = 1e-6
            self.ctx.raspa_parameters['GeneralSettings']['UseChargesFromCIFFile'] = 'yes'
        else:
            self.ctx.raspa_parameters['GeneralSettings']['UseChargesFromCIFFile'] = 'no'

        self.ctx.restart_raspa_calc = None

        self.ctx.zeopp_options = self.inputs.zeopp_options
        self.ctx.raspa_options = self.inputs.raspa_options

    def run_zeopp(self):
        """Function that performs zeo++ volpo, sa and block calculations."""
        for key, value in self.ctx.raspa_comp.items():
            if key in list(self.inputs.raspa_comp):
                comp_name = value.name
                probe_radius = value.radius
                params = {
                    'ha': self.inputs.zeopp_parameters['accuracy'],
                    'sa': [
                        probe_radius,
                        probe_radius,
                        self.inputs.zeopp_parameters['sa_samples'],
                    ],
                    'block': [
                        probe_radius,
                        self.inputs.zeopp_parameters['block_samples'],
                    ],
                    'volpo': [
                        probe_radius,
                        probe_radius,
                        self.inputs.zeopp_parameters['volpo_samples'],
                    ],
                }

                inputs = {
                    'code': self.inputs.zeopp_code,
                    'structure': self.inputs.structure,
                    'parameters': NetworkParameters(dict=params).store(),
                    'metadata': {
                        'options':
                            self.ctx.zeopp_options,
                        'label':
                            'ZeoppVolpoBlock',
                        'description':
                            'Zeo++ calculation (sa, volpo, block) for structure {}'.format(self.inputs.structure.label),
                    },
                }

                # Use default zeopp atomic radii only if a .rad file is not specified
                try:
                    inputs['atomic_radii'] = self.inputs.zeopp_atomic_radii
                    self.report('Zeo++ will use atomic radii from the .rad file')
                except:
                    self.report('Zeo++ will use default atomic radii')

                # Create the calculation process and submit it
                zeopp_full = self.submit(ZeoppCalculation, **inputs)
                zeopp_label = 'zeopp_{}'.format(comp_name)
                self.report('pk: {} | Running Zeo++ volpo, sa and block calculations'.format(zeopp_full.pk))
                return ToContext(**{zeopp_label: zeopp_full})

    def inspect_zeopp_calc(self):
        """Fail early if already Zeo++ fails. Extract blocked pockets."""
        for key, value in self.ctx.raspa_comp.items():
            if key in list(self.inputs.raspa_comp):
                comp_name = value.name
                zeopp_label = 'zeopp_{}'.format(comp_name)
                self.report('Checking if {} Zeo++ job finished OK'.format(zeopp_label))
                assert self.ctx[zeopp_label].is_finished_ok

        self.ctx.blocked_pockets = {}
        self.ctx.number_blocking_spheres = {}

        for key, value in self.ctx.raspa_comp.items():
            if key in list(self.inputs.raspa_comp):
                comp_name = value.name
                zeopp_label = 'zeopp_{}'.format(comp_name)
                bp_label = '_'.join((self.inputs.structure.label, comp_name))
                bp_dir = self.ctx[zeopp_label].outputs.retrieved._repository._get_base_folder().abspath
                bp_filename = ''.join([bp_label, '.block'])
                os.rename(os.path.join(bp_dir, 'out.block'), os.path.join(bp_dir, bp_filename))
                bp_path = os.path.join(bp_dir, bp_label + '.block')

                with open(bp_path, 'r') as block_file:
                    self.ctx.number_blocking_spheres[comp_name] = int(block_file.readline().strip())
                    if self.ctx.number_blocking_spheres[comp_name] > 0:
                        self.ctx.raspa_parameters['Component'][comp_name]['BlockPocketsFileName'] = {}
                        self.ctx.raspa_parameters['Component'][comp_name]['BlockPocketsFileName'][
                            self.inputs.structure.label] = bp_label

                        # This creates the link but the file is not retrieved to be used.
                        inputs['block_pocket'][bp_label] = self.ctx[zeopp_label].outputs.block

                        self.report('{} blocking spheres are present for {} and used for RASPA'.format(
                            self.ctx.number_blocking_spheres[comp_name], comp_name))
                    else:
                        self.report('No blocking spheres found for {}'.format(comp_name))

    def init_raspa_calc(self):
        """Parse the output of Zeo++ and instruct the input for RASPA. """

        # Create the component dictionary for RASPA
        for key, value in self.ctx.raspa_comp.items():
            if key in list(self.inputs.raspa_comp):
                comp_name = value.name
                mol_def = value.mol_def
                bp_label = '_'.join((self.inputs.structure.label, comp_name))
                self.ctx.raspa_parameters['Component'][comp_name] = self.ctx.raspa_parameters['Component'].pop(key)
                self.ctx.raspa_parameters['Component'][comp_name]['MoleculeDefinition'] = mol_def

                comp_name = value.name
                mol_frac = value.mol_fraction
                singlebead = value.singlebead
                self.ctx.raspa_parameters['Component'][comp_name]['MolFraction'] = float(mol_frac)
                self.ctx.raspa_parameters['Component'][comp_name]['TranslationProbability'] = 0.5

                # Only adds RotationProbability move if it is not singlebead model.
                if not singlebead:
                    self.ctx.raspa_parameters['Component'][comp_name]['RotationProbability'] = 0.5
                self.ctx.raspa_parameters['Component'][comp_name]['ReinsertionProbability'] = 0.5
                self.ctx.raspa_parameters['Component'][comp_name]['SwapProbability'] = 1.0
                self.ctx.raspa_parameters['Component'][comp_name]['IdentityChangeProbability'] = 1.0
                self.ctx.raspa_parameters['Component'][comp_name]['NumberOfIdentityChanges'] = len(
                    list(self.inputs.raspa_comp))
                self.ctx.raspa_parameters['Component'][comp_name]['IdentityChangesList'] = [
                    i for i in range(len(list(self.inputs.raspa_comp)))
                ]

        cutoff = self.ctx.raspa_parameters['GeneralSettings']['CutOff']
        self.ctx.ucs = multiply_unit_cell(self.inputs.structure, cutoff * 2)
        self.ctx.raspa_parameters['System'][self.inputs.structure.label]['UnitCells'] = '{} {} {}'.format(
            self.ctx.ucs[0], self.ctx.ucs[1], self.ctx.ucs[2])

        self.ctx.raspa_parameters['GeneralSettings']['PrintEvery'] = int(
            self.ctx.raspa_parameters['GeneralSettings']['NumberOfCycles'] / self.inputs.raspa_verbosity)

        self.ctx.raspa_parameters['GeneralSettings']['PrintPropertiesEvery'] = int(
            self.ctx.raspa_parameters['GeneralSettings']['NumberOfCycles'] / self.inputs.raspa_verbosity)

        self.ctx.raspa_parameters_0 = deepcopy(self.ctx.raspa_parameters)  # make copy to stay safe

    def should_run_loading_raspa(self):
        """We run another raspa calculation only if the current iteration is smaller than
        the total number of pressures we want to compute."""

        self.report('checking if need to run more cycle. Current run {}'.format(self.ctx.counter))

        if self.ctx.counter < 1:
            return True
        # First check is cycles > min cycles
        if self.ctx.cycles > self.ctx.min_cycles:
            # If this is the case, get the relative changes. Get the largest one,
            # check if below threshold
            converged = []
            output_raspa_loading = (self.ctx.raspa_loading.outputs.output_parameters.get_dict())
            self.ctx.restart_raspa_calc = self.ctx.raspa_loading.outputs['retrieved']
            for key, value in self.ctx.raspa_comp.items():
                if key in list(self.inputs.raspa_comp):
                    comp_name = value.name
                    conv_threshold = value.conv_threshold
                    loading_previous = self.ctx.loading[comp_name][-2]
                    loading_current = self.ctx.loading[comp_name][-1]

                    percentage_change = (np.abs(loading_previous - loading_current) / loading_current) * 100
                    percentage_error = self.ctx.loading_dev[comp_name][-1] / loading_current * 100

                    if (percentage_change  < conv_threshold) & (percentage_error  < conv_threshold):
                        converged.append(True)
                    else:
                        converged.append(False)

            if all(converged):
                self.report('all loadings are converged')
                return False  # all components are converged
            else:
                self.report('loadings are not yet converged')
                return True
        else:  # minimum number of cycles not reached
            self.report('minimum number of {} cycles not reached yet, current number of cycles {}'.format(
                self.ctx.min_cycles.value, self.ctx.cycles))
            return True

    def run_first_gcmc(self):
        """This function will run RaspaConvergeWorkChain for the current pressure"""
        self.ctx.raspa_parameters['System'][self.inputs.structure.label]['ExternalPressure'] = self.ctx.pressure

        parameters = ParameterData(dict=self.ctx.raspa_parameters_0).store()
        # Create the input dictionary
        inputs = {
            'code': self.inputs.raspa_code,
            'framework': {
                self.inputs.structure.label: self.ctx.structure
            },
            'parameters': parameters,
            'metadata': {
                'options':
                    self.ctx.raspa_options,
                'label':
                    'run_first_loading_raspa',
                'description':
                    'first RASPA calculation in ConvergeLoadingWorkchain for {}'.format(self.inputs.structure.label),
            },
        }
        inputs['block_pocket'] = self.ctx.blocked_pockets

        # Create the calculation process and launch it
        gcmc = self.submit(RaspaCalculation, **inputs)
        self.ctx.counter += 1
        self.ctx.cycles += self.ctx.raspa_parameters['GeneralSettings']['NumberOfCycles']
        self.report('pk: {} | Running first RASPA GCMC'.format(gcmc.pk))
        return ToContext(raspa_loading=gcmc)

    def run_loading_raspa(self):
        """This function will run RaspaConvergeWorkChain for the current pressure"""
        self.ctx.raspa_parameters['GeneralSettings']['NumberOfInitializationCycles'] = 0
        self.ctx.raspa_parameters['System'][self.inputs.structure.label]['ExternalPressure'] = self.ctx.pressure
        self.ctx.counter += 1
        self.ctx.cycles += self.ctx.raspa_parameters['GeneralSettings']['NumberOfCycles']

        parameters = ParameterData(dict=self.ctx.raspa_parameters).store()
        # Create the input dictionary
        inputs = {
            'code': self.inputs.raspa_code,
            'framework': {
                self.inputs.structure.label: self.ctx.structure
            },
            'parameters': parameters,
            'metadata': {
                'options':
                    self.ctx.raspa_options,
                'label':
                    'run_loading_raspa',
                'description':
                    'RASPA #{} calculation in ConvergeLoadingWorkchain for {}'.format(
                        self.ctx.counter, self.inputs.structure.label),
            },
        }

        inputs['block_pocket'] = self.ctx.blocked_pockets
        if self.ctx.restart_raspa_calc is not None:
            inputs['retrieved_parent_folder'] = self.ctx.restart_raspa_calc

        # Create the calculation process and launch it
        gcmc = self.submit(RaspaCalculation, **inputs)

        self.report('pk: {} | Running RASPA GCMC for the {} time'.format(gcmc.pk, self.ctx.counter))
        return ToContext(raspa_loading=gcmc)

    def parse_loading_raspa(self):
        output_gcmc = self.ctx.raspa_loading.outputs.output_parameters.get_dict()
        for key, value in self.ctx.raspa_comp.items():
            if key in list(self.inputs.raspa_comp):
                comp_name = value.name
                mol_frac = value.mol_fraction
                self.ctx.loading[comp_name].append(
                    output_gcmc[self.inputs.structure.label]['components'][comp_name]['loading_absolute_average'])
                self.ctx.loading_dev[comp_name].append(
                    output_gcmc[self.inputs.structure.label]['components'][comp_name]['loading_absolute_dev'])

                self.ctx.adsorbate_density_average[comp_name].append(
                    output_gcmc[self.inputs.structure.label]['components'][comp_name]['adsorbate_density_average'])
                self.ctx.adsorbate_density_dev[comp_name].append(
                    output_gcmc[self.inputs.structure.label]['components'][comp_name]['adsorbate_density_dev'])

            # Keeping track of total energies
            self.ctx.total_energy_average.append(
                output_gcmc[self.inputs.structure.label]['general']['total_energy_average'])
            self.ctx.total_energy_dev.append(output_gcmc[self.inputs.structure.label]['general']['total_energy_dev'])

            # Keeping track of host-ads energies
            self.ctx.host_ads_total_energy_average.append(
                output_gcmc[self.inputs.structure.label]['general']['host_ads_total_energy_average'])
            self.ctx.host_ads_total_energy_dev.append(
                output_gcmc[self.inputs.structure.label]['general']['host_ads_total_energy_dev'])

            self.ctx.host_ads_vdw_energy_average.append(
                output_gcmc[self.inputs.structure.label]['general']['host_ads_vdw_energy_average'])
            self.ctx.host_ads_vdw_energy_dev.append(
                output_gcmc[self.inputs.structure.label]['general']['host_ads_vdw_energy_dev'])

            self.ctx.host_ads_coulomb_energy_average.append(
                output_gcmc[self.inputs.structure.label]['general']['host_ads_coulomb_energy_average'])
            self.ctx.host_ads_coulomb_energy_dev.append(
                output_gcmc[self.inputs.structure.label]['general']['host_ads_coulomb_energy_dev'])

            # Keeping track of ads-ads energies
            self.ctx.ads_ads_total_energy_average.append(
                output_gcmc[self.inputs.structure.label]['general']['ads_ads_total_energy_average'])

            self.ctx.ads_ads_total_energy_dev.append(
                output_gcmc[self.inputs.structure.label]['general']['ads_ads_total_energy_dev'])

            self.ctx.ads_ads_coulomb_energy_average.append(
                output_gcmc[self.inputs.structure.label]['general']['ads_ads_coulomb_energy_average'])
            self.ctx.ads_ads_coulomb_energy_dev.append(
                output_gcmc[self.inputs.structure.label]['general']['ads_ads_coulomb_energy_dev'])

            self.ctx.ads_ads_vdw_energy_average.append(
                output_gcmc[self.inputs.structure.label]['general']['ads_ads_vdw_energy_average'])
            self.ctx.ads_ads_vdw_energy_dev.append(
                output_gcmc[self.inputs.structure.label]['general']['ads_ads_vdw_energy_dev'])

            self.ctx.enthalpy_of_adsorption_average.append(
                output_gcmc[self.inputs.structure.label]['general']['enthalpy_of_adsorption_average'])

            self.ctx.enthalpy_of_adsorption_dev.append(
                output_gcmc[self.inputs.structure.label]['general']['enthalpy_of_adsorption_dev'])

    def return_results(self):
        """Attach the results to the output."""

        result_dict = {}

        # RASPA
        result_dict['pressure'] = (
            self.ctx.raspa_parameters['System'][self.inputs.structure.label]['ExternalPressure'] / 1e5)
        result_dict['pressure_unit'] = 'bar'

        result_dict['temperature'] = self.ctx.raspa_parameters['System'][
            self.inputs.structure.label]['ExternalTemperature']
        result_dict['temperature_unit'] = 'K'

        # General, resubmission-run independent RASPA parameters
        result_dict['conversion_factor_molec_uc_to_cm3stp_cm3'] = {}
        result_dict['conversion_factor_molec_uc_to_gr_gr'] = {}
        result_dict['conversion_factor_molec_uc_to_mol_kg'] = {}
        result_dict['mol_fraction'] = {}
        output_gcmc = self.ctx.raspa_loading.outputs.output_parameters.get_dict()
        for key, value in self.ctx.raspa_comp.items():
            if key in list(self.inputs.raspa_comp):
                comp_name = value.name
                mol_frac = value.mol_fraction
                result_dict['conversion_factor_molec_uc_to_cm3stp_cm3'][comp_name] = output_gcmc[
                    self.inputs.structure.label]['components'][comp_name]['conversion_factor_molec_uc_to_cm3stp_cm3']
                result_dict['conversion_factor_molec_uc_to_gr_gr'][comp_name] = output_gcmc[
                    self.inputs.structure.label]['components'][comp_name]['conversion_factor_molec_uc_to_gr_gr']
                result_dict['conversion_factor_molec_uc_to_mol_kg'][comp_name] = output_gcmc[
                    self.inputs.structure.label]['components'][comp_name]['conversion_factor_molec_uc_to_mol_kg']
                result_dict['mol_fraction'][comp_name] = output_gcmc[
                    self.inputs.structure.label]['components'][comp_name]['mol_fraction']

        result_dict['loading_absolute_average'] = dict(self.ctx.loading)
        result_dict['loading_absolute_dev'] = dict(self.ctx.loading_dev)
        result_dict['loading_absolute_units'] = 'molec/uc'

        result_dict['adsorbate_density_average'] = dict(self.ctx.adsorbate_density_average)
        result_dict['adsorbate_density_dev'] = dict(self.ctx.adsorbate_density_dev)
        result_dict['adsorbate_density_units'] = 'kg/m^3'

        result_dict['host_ads_total_energy_unit'] = 'kJ/mol'
        result_dict['host_ads_vdw_energy_unit'] = 'kJ/mol'
        result_dict['total_energy_average_unit'] = 'K'

        result_dict['total_energy_average'] = self.ctx.total_energy_average
        result_dict['total_energy_dev'] = self.ctx.total_energy_dev

        result_dict['host_ads_total_energy_average'] = self.ctx.host_ads_total_energy_average
        result_dict['host_ads_total_energy_dev'] = self.ctx.host_ads_total_energy_dev

        result_dict['host_ads_vdw_energy_average'] = self.ctx.host_ads_vdw_energy_average
        result_dict['host_ads_vdw_energy_dev'] = self.ctx.host_ads_vdw_energy_dev

        result_dict['host_ads_coulomb_energy_average'] = self.ctx.host_ads_coulomb_energy_average
        result_dict['host_ads_coulomb_energy_dev'] = self.ctx.host_ads_coulomb_energy_dev

        result_dict['ads_ads_total_energy_average'] = self.ctx.ads_ads_total_energy_average
        result_dict['ads_ads_total_energy_dev'] = self.ctx.ads_ads_total_energy_dev

        result_dict['ads_ads_coulomb_energy_average'] = self.ctx.ads_ads_coulomb_energy_average
        result_dict['ads_ads_coulomb_energy_dev'] = self.ctx.ads_ads_coulomb_energy_dev

        result_dict['ads_ads_vdw_energy_average'] = self.ctx.ads_ads_vdw_energy_average
        result_dict['ads_ads_vdw_energy_dev'] = self.ctx.ads_ads_vdw_energy_dev

        result_dict['enthalpy_of_adsorption_average'] = self.ctx.enthalpy_of_adsorption_average
        result_dict['enthalpy_of_adsorption_dev'] = self.ctx.enthalpy_of_adsorption_dev
        result_dict['enthalpy_of_adsorption_unit'] = 'K'

        result_dict['uc_multipliers'] = self.ctx.ucs

        # Zeo++
        result_dict['poav_fraction'] = {}
        result_dict['ponav_fraction'] = {}
        result_dict['gpoav'] = {}
        result_dict['gasa'] = {}
        result_dict['vasa'] = {}
        result_dict['gnasa'] = {}
        result_dict['vnasa'] = {}
        result_dict['channel_surface_area'] = {}
        result_dict['pocket_surface_area'] = {}
        result_dict['number_blocking_spheres'] = {}
        result_dict['density_unit'] = 'g/cm^3'
        result_dict['gpoav_unit'] = 'cm^3/g'
        result_dict['gasa_unit'] = 'm^2/g'
        result_dict['vasa_unit'] = 'm^2/cm^3'
        result_dict['gnasa_unit'] = 'm^2/g'
        result_dict['vnasa_unit'] = 'ASA_m^2/cm^3'
        result_dict['channel_surface_area_unit'] = 'A^2'
        result_dict['pocket_surface_area_unit'] = 'A^2'

        for key, value in self.ctx.raspa_comp.items():
            if key in list(self.inputs.raspa_comp):
                comp_name = value.name
                zeopp_label = 'zeopp_{}'.format(comp_name)
                output_zeo = self.ctx[zeopp_label].outputs.output_parameters.get_dict()
                result_dict['poav_fraction'][comp_name] = output_zeo['POAV_Volume_fraction']
                result_dict['ponav_fraction'][comp_name] = output_zeo['PONAV_Volume_fraction']
                result_dict['gpoav'][comp_name] = output_zeo['POAV_cm^3/g']
                result_dict['gasa'][comp_name] = output_zeo['ASA_m^2/g']
                result_dict['vasa'][comp_name] = output_zeo['ASA_m^2/cm^3']
                result_dict['gnasa'][comp_name] = output_zeo['NASA_m^2/g']
                result_dict['vnasa'][comp_name] = output_zeo['NASA_m^2/cm^3']
                result_dict['channel_surface_area'][comp_name] = output_zeo['Channel_surface_area_A^2']
                result_dict['pocket_surface_area'][comp_name] = output_zeo['Pocket_surface_area_A^2']
                result_dict['number_blocking_spheres'][comp_name] = self.ctx.number_blocking_spheres[comp_name]
                result_dict['density'] = output_zeo['Density']

        self.out('results', ParameterData(dict=result_dict).store())
        self.report('ConvergeLoadingWorkchain completed successfully. | Result Dict is <{}>'.format(
            self.outputs['results'].pk))
        return
