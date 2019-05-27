#!/usr/bin/python2
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
from aiida.work.run import submit
from aiida.work.workchain import WorkChain, ToContext, while_, Outputs
from aiida_raspa.workflows import RaspaConvergeWorkChain
import numpy as np
np.random.seed(42)
from numpy.random import randint

ZeoppCalculation = CalculationFactory('zeopp.network')

# data objects
ArrayData = DataFactory('array')
CifData = DataFactory('cif')
NetworkParameters = DataFactory('zeopp.parameters')
ParameterData = DataFactory('parameter')
RemoteData = DataFactory('remote')
StructureData = DataFactory('structure')
SinglefileData = DataFactory('singlefile')


class GCMCMD2(WorkChain):
    @classmethod
    def define(cls, spec):
        super(GCMCMD2, cls).define(spec)

        # structure, adsorbant, pressures
        spec.input('structure', valid_type=CifData)
        spec.input("pressure", valid_type=Float, required=True)
        spec.input("number_runs", valid_type=Float, default=1)
        spec.input("number_cycles_lower", valid_type=Float, default=1)
        spec.input("number_cycles_upper", valid_type=Float, default=100000)

        # zeopp
        spec.input('zeopp_code', valid_type=Code)
        spec.input("_zeopp_options",
                   valid_type=dict,
                   default=None,
                   required=False)
        spec.input("zeopp_probe_radius", valid_type=Float)
        spec.input("zeopp_atomic_radii",
                   valid_type=SinglefileData,
                   default=None,
                   required=False)

        # raspa
        spec.input("raspa_code", valid_type=Code)
        spec.input("raspa_parameters_gcmc", valid_type=ParameterData)
        spec.input("raspa_parameters_md", valid_type=ParameterData)
        spec.input("raspa_parameters_gcmc_0", valid_type=ParameterData)
        spec.input("_raspa_options",
                   valid_type=dict,
                   default=None,
                   required=False)

        # settings
        spec.input("_usecharges",
                   valid_type=bool,
                   default=True,
                   required=False)

        # workflow
        spec.outline(
            cls.init,
            cls.run_zeopp,  # computes volpo and block pockets
            cls.init_raspa_calc,  # assign HeliumVoidFraction=POAV
            cls.run_first_gcmc,  # first GCMC is longer and with intialization
            cls.
            parse_loading_raspa,  # then move to loop in which one cycles between MD and MC
            while_(cls.should_run_loading_raspa)(
                cls.run_md,
                cls.parse_loading_raspa,
                cls.
                run_loading_raspa,  # for each run, recover the last snapshot of the previous and run GCMC
                cls.parse_loading_raspa,
            ),
            cls.return_results,
        )

        spec.dynamic_output()

    def init(self):
        """Initialize variables and the pressures we want to compute"""
        self.ctx.structure = self.inputs.structure
        self.ctx.pressure = self.inputs.pressure
        self.ctx.number_runs = self.inputs.number_runs
        self.ctx.cycles_lower = self.inputs.number_cycles_lower
        self.ctx.cycles_upper = self.inputs.number_cycles_upper
        self.ctx.current_run_counter = -1  # start at minus one for the first GCMC with initalization cycle
        self.ctx.current_run = -1
        self.ctx.loading = {}
        self.ctx.loading_dev = {}
        self.ctx.enthalpy_of_adsorption = {}
        self.ctx.enthalpy_of_adsorption_dev = {}
        self.ctx.rdfs = {}
        self.ctx.mc_statistics = {}
        self.ctx.raspa_warnings = {}
        self.ctx.ads_ads_coulomb_energy_average = {}
        self.ctx.ads_ads_coulomb_energy_dev = {}
        self.ctx.ads_ads_total_energy_average = {}
        self.ctx.ads_ads_total_energy_dev = {}
        self.ctx.ads_ads_vdw_energy_average = {}
        self.ctx.ads_ads_vdw_energy_dev = {}
        self.ctx.host_ads_coulomb_energy_average = {}
        self.ctx.host_ads_coulomb_energy_dev = {}
        self.ctx.host_ads_total_energy_average = {}
        self.ctx.host_ads_total_energy_dev = {}
        self.ctx.host_ads_vdw_energy_average = {}
        self.ctx.host_ads_vdw_energy_dev = {}
        self.ctx.total_energy_average = {}
        self.ctx.total_energy_dev = {}
        self.ctx.tail_correction_energy_average = {}
        self.ctx.tail_correction_energy_dev = {}

        self.ctx.raspa_parameters_gcmc = self.inputs.raspa_parameters_gcmc.get_dict(
        )
        self.ctx.raspa_parameters_gcmc_0 = self.inputs.raspa_parameters_gcmc_0.get_dict(
        )
        self.ctx.raspa_parameters_md = self.inputs.raspa_parameters_md.get_dict(
        )

        if self.inputs._usecharges:
            self.ctx.raspa_parameters_gcmc['ChargeMethod'] = "Ewald"
            self.ctx.raspa_parameters_gcmc['EwaldPrecision'] = 1e-6
            self.ctx.raspa_parameters_gcmc['GeneralSettings'][
                'UseChargesFromCIFFile'] = "yes"

            self.ctx.raspa_parameters_gcmc_0['ChargeMethod'] = "Ewald"
            self.ctx.raspa_parameters_gcmc_0['EwaldPrecision'] = 1e-6
            self.ctx.raspa_parameters_gcmc_0['GeneralSettings'][
                'UseChargesFromCIFFile'] = "yes"

            self.ctx.raspa_parameters_md['ChargeMethod'] = "Ewald"
            self.ctx.raspa_parameters_md['EwaldPrecision'] = 1e-6
            self.ctx.raspa_parameters_md['GeneralSettings'][
                'UseChargesFromCIFFile'] = "yes"

        else:
            self.ctx.raspa_parameters_gcmc['GeneralSettings'][
                'UseChargesFromCIFFile'] = "no"
            self.ctx.raspa_parameters_gcmc_0['GeneralSettings'][
                'UseChargesFromCIFFile'] = "no"
            self.ctx.raspa_parameters_md['GeneralSettings'][
                'UseChargesFromCIFFile'] = "no"

        self.ctx.restart_raspa_calc = None

    def run_zeopp(self):
        """Main function that performs zeo++ VOLPO and block calculations."""
        params = {
            'ha':
            True,
            # 100 samples / Ang^3: accurate for all the structures
            'block': [self.inputs.zeopp_probe_radius.value, 100],
            # 100k samples, may need more for structures bigger than 30x30x30
            'volpo': [
                self.inputs.zeopp_probe_radius.value,
                self.inputs.zeopp_probe_radius.value, 100000
            ]
        }

        inputs = {
            'code': self.inputs.zeopp_code,
            'structure': self.inputs.structure,
            'parameters': NetworkParameters(dict=params).store(),
            '_options': self.inputs._zeopp_options,
            '_label': "ZeoppVolpoBlock",
        }

        # Use default zeopp atomic radii only if a .rad file is not specified
        try:
            inputs['atomic_radii'] = self.inputs.zeopp_atomic_radii
            self.report("Zeopp will use atomic radii from the .rad file")
        except:
            self.report("Zeopp will use default atomic radii")

        # Create the calculation process and launch it
        running = submit(ZeoppCalculation.process(), **inputs)
        self.report(
            "pk: {} | Running zeo++ volpo and block calculations".format(
                running.pid))
        return ToContext(zeopp=Outputs(running))

    def init_raspa_calc(self):
        """Parse the output of Zeo++ and instruct the input for Raspa. """
        # Use probe-occupiable available void fraction as the helium void fraction (for excess uptake)
        self.ctx.raspa_parameters_gcmc['GeneralSettings'][
            'HeliumVoidFraction'] = self.ctx.zeopp[
                'output_parameters'].get_dict()['POAV_Volume_fraction']
        self.ctx.raspa_parameters_gcmc_0['GeneralSettings'][
            'HeliumVoidFraction'] = self.ctx.zeopp[
                'output_parameters'].get_dict()['POAV_Volume_fraction']
        self.ctx.raspa_parameters_md['GeneralSettings'][
            'HeliumVoidFraction'] = self.ctx.zeopp[
                'output_parameters'].get_dict()['POAV_Volume_fraction']

    def should_run_loading_raspa(self):
        """We run another raspa calculation only if the current iteration is smaller than
        the total number of pressures we want to compute."""
        self.report(
            'checking if need to run more cycle. Total number of runs {}, current run {}'
            .format(self.ctx.number_runs, self.ctx.current_run_counter))
        return self.ctx.current_run_counter < self.ctx.number_runs

    def run_first_gcmc(self):
        """This function will run RaspaConvergeWorkChain for the current pressure"""
        self.ctx.raspa_parameters_gcmc_0['GeneralSettings'][
            'ExternalPressure'] = self.ctx.pressure

        parameters = ParameterData(
            dict=self.ctx.raspa_parameters_gcmc_0).store()
        # Create the input dictionary
        inputs = {
            'code': self.inputs.raspa_code,
            'structure': self.ctx.structure,
            'parameters': parameters,
            '_options': self.inputs._raspa_options,
            '_label': "run_first_loading_raspa",
        }
        # Check if there are pocket blocks to be loaded
        try:
            inputs['block_component_0'] = self.ctx.zeopp['block']
        except Exception:
            pass

        if self.ctx.restart_raspa_calc is not None:
            inputs['retrieved_parent_folder'] = self.ctx.restart_raspa_calc

        # Create the calculation process and launch it
        running = submit(RaspaConvergeWorkChain, **inputs)
        self.ctx.current_run_counter += 1
        self.report("pk: {} | Running RASPA  for the {} time".format(
            running.pid, self.ctx.current_run_counter))

        return ToContext(raspa_loading=Outputs(running))

    def run_md(self):
        """This function will run RaspaConvergeWorkChain for the current pressure"""
        self.ctx.raspa_parameters_md['GeneralSettings'][
            "NumberOfInitializationCycles"] = 0

        num_cycles = randint(self.ctx.cycles_lower, self.ctx.cycles_upper)
        self.ctx.raspa_parameters_md['GeneralSettings'][
            "NumberOfCycles"] = num_cycles
        self.ctx.raspa_parameters_md['GeneralSettings'][
            "WriteRDFEvery"] = num_cycles

        # Let's hardcode some stuff to be sure for development, I am especially not sure if the restart function
        # would work otherwise (i.e. if there is no pressure in GeneralSettings

        self.ctx.raspa_parameters_md['GeneralSettings']["Ensemble"] = 'NVT'
        self.ctx.raspa_parameters_md['GeneralSettings']['ExternalPressure'] = 0

        parameters = ParameterData(dict=self.ctx.raspa_parameters_md).store()
        # Create the input dictionary
        inputs = {
            'code': self.inputs.raspa_code,
            'structure': self.ctx.structure,
            'parameters': parameters,
            '_options': self.inputs._raspa_options,
            '_label': "run_md_raspa",
        }

        if self.ctx.restart_raspa_calc is not None:
            inputs['retrieved_parent_folder'] = self.ctx.restart_raspa_calc

        # Create the calculation process and launch it
        running = submit(RaspaConvergeWorkChain, **inputs)
        self.ctx.current_run_counter += 1
        self.ctx.current_run = str('md' + str(self.ctx.current_run_counter))
        self.report("pk: {} | Running RASPA MD for the {} time".format(
            running.pid, self.ctx.current_run_counter))

        return ToContext(raspa_loading=Outputs(running))

    def run_loading_raspa(self):
        """This function will run RaspaConvergeWorkChain for the current pressure"""
        self.ctx.raspa_parameters_gcmc['GeneralSettings'][
            "NumberOfInitializationCycles"] = 0
        self.ctx.raspa_parameters_gcmc['GeneralSettings'][
            'ExternalPressure'] = self.ctx.pressure

        parameters = ParameterData(dict=self.ctx.raspa_parameters_gcmc).store()
        # Create the input dictionary
        inputs = {
            'code':
            self.inputs.raspa_code,
            'structure':
            self.ctx.structure,
            'parameters':
            parameters,
            '_options':
            self.inputs._raspa_options,
            '_label':
            "run_loading_raspa",
            'settings':
            ParameterData(
                dict={
                    'additional_retrieve_list':
                    ['RadialDistributionFunctions/System_0/*'],
                })
        }
        # Check if there are pocket blocks to be loaded
        try:
            inputs['block_component_0'] = self.ctx.zeopp['block']
        except Exception:
            pass

        if self.ctx.restart_raspa_calc is not None:
            inputs['retrieved_parent_folder'] = self.ctx.restart_raspa_calc

        # Create the calculation process and launch it
        running = submit(RaspaConvergeWorkChain, **inputs)
        self.ctx.current_run = str('gcmc' + str(self.ctx.current_run_counter))
        self.report("pk: {} | Running RASPA for for the {} time".format(
            running.pid, self.ctx.current_run_counter))

        return ToContext(raspa_loading=Outputs(running))

    def parse_loading_raspa(self):
        """Extract the pressure and loading average of the last completed raspa calculation"""
        self.ctx.restart_raspa_calc = self.ctx.raspa_loading[
            'retrieved_parent_folder']
        loading_average = self.ctx.raspa_loading[
            "component_0"].dict.loading_absolute_average
        loading_dev = self.ctx.raspa_loading[
            "component_0"].dict.loading_absolute_dev
        enthalpy_of_adsorption = self.ctx.raspa_loading[
            "output_parameters"].dict.enthalpy_of_adsorption_average
        enthalpy_of_adsorption_dev = self.ctx.raspa_loading[
            "output_parameters"].dict.enthalpy_of_adsorption_dev

        ads_ads_coulomb_energy_average = self.ctx.raspa_loading[
            "output_parameters"].dict.ads_ads_coulomb_energy_average
        ads_ads_coulomb_energy_dev = self.ctx.raspa_loading[
            "output_parameters"].dict.ads_ads_coulomb_energy_dev
        ads_ads_total_energy_average = self.ctx.raspa_loading[
            "output_parameters"].dict.ads_ads_total_energy_average
        ads_ads_total_energy_dev = self.ctx.raspa_loading[
            "output_parameters"].dict.ads_ads_total_energy_dev
        ads_ads_vdw_energy_average = self.ctx.raspa_loading[
            "output_parameters"].dict.ads_ads_vdw_energy_average
        ads_ads_vdw_energy_dev = self.ctx.raspa_loading[
            "output_parameters"].dict.ads_ads_vdw_energy_dev
        host_ads_coulomb_energy_average = self.ctx.raspa_loading[
            "output_parameters"].dict.host_ads_coulomb_energy_average
        host_ads_coulomb_energy_dev = self.ctx.raspa_loading[
            "output_parameters"].dict.host_ads_coulomb_energy_dev
        host_ads_total_energy_average = self.ctx.raspa_loading[
            "output_parameters"].dict.host_ads_total_energy_average
        host_ads_total_energy_dev = self.ctx.raspa_loading[
            "output_parameters"].dict.host_ads_total_energy_dev
        host_ads_vdw_energy_average = self.ctx.raspa_loading[
            "output_parameters"].dict.host_ads_vdw_energy_average
        host_ads_vdw_energy_dev = self.ctx.raspa_loading[
            "output_parameters"].dict.host_ads_vdw_energy_dev
        total_energy_average = self.ctx.raspa_loading[
            "output_parameters"].dict.total_energy_average
        total_energy_dev = self.ctx.raspa_loading[
            "output_parameters"].dict.total_energy_dev

        rdfs = self.ctx.raspa_loading["output_parameters"].dict.rdfs
        mc_statistics = self.ctx.raspa_loading[
            'output_parameters'].dict.mc_move_statistics
        raspa_warnings = self.ctx.raspa_loading[
            'output_parameters'].dict.warnings
        tail_correction_energy_average = self.ctx.raspa_loading[
            'output_parameters'].dict.tail_correction_energy_average
        tail_correction_energy_dev = self.ctx.raspa_loading[
            'output_parameters'].dict.tail_correction_energy_dev

        curr_run = str(self.ctx.current_run)
        self.ctx.tail_correction_energy_average[
            curr_run] = tail_correction_energy_average
        self.ctx.tail_correction_energy_dev[
            curr_run] = tail_correction_energy_dev
        self.ctx.raspa_warnings[curr_run] = raspa_warnings
        self.ctx.loading[curr_run] = loading_average
        self.ctx.mc_statistics[curr_run] = mc_statistics

        self.ctx.loading_dev[curr_run] = loading_dev
        self.ctx.enthalpy_of_adsorption[curr_run] = enthalpy_of_adsorption
        self.ctx.enthalpy_of_adsorption_dev[
            curr_run] = enthalpy_of_adsorption_dev
        self.ctx.rdfs[curr_run] = rdfs

        self.ctx.ads_ads_coulomb_energy_average[
            curr_run] = ads_ads_coulomb_energy_average
        self.ctx.ads_ads_coulomb_energy_dev[
            curr_run] = ads_ads_coulomb_energy_dev
        self.ctx.ads_ads_total_energy_average[
            curr_run] = ads_ads_total_energy_average
        self.ctx.ads_ads_total_energy_dev[curr_run] = ads_ads_total_energy_dev
        self.ctx.ads_ads_vdw_energy_average[
            curr_run] = ads_ads_vdw_energy_average
        self.ctx.ads_ads_vdw_energy_dev[curr_run] = ads_ads_vdw_energy_dev
        self.ctx.host_ads_coulomb_energy_average[
            curr_run] = host_ads_coulomb_energy_average
        self.ctx.host_ads_coulomb_energy_dev[
            curr_run] = host_ads_coulomb_energy_dev
        self.ctx.host_ads_total_energy_average[
            curr_run] = host_ads_total_energy_average
        self.ctx.host_ads_total_energy_dev[
            curr_run] = host_ads_total_energy_dev
        self.ctx.host_ads_vdw_energy_average[
            curr_run] = host_ads_vdw_energy_average
        self.ctx.host_ads_vdw_energy_dev[curr_run] = host_ads_vdw_energy_dev
        self.ctx.total_energy_average[curr_run] = total_energy_average
        self.ctx.total_energy_dev[curr_run] = total_energy_dev

    def return_results(self):
        """Attach the results to the output."""

        result_dict = {}

        # Zeopp section
        result_dict['Density'] = self.ctx.zeopp['output_parameters'].get_dict(
        )['Density']
        result_dict['Density_unit'] = "g/cm^3"
        result_dict['POAV_Volume_fraction'] = self.ctx.zeopp[
            'output_parameters'].get_dict()['POAV_Volume_fraction']
        result_dict['PONAV_Volume_fraction'] = self.ctx.zeopp[
            'output_parameters'].get_dict()['PONAV_Volume_fraction']
        result_dict['POAV_cm^3/g'] = self.ctx.zeopp[
            'output_parameters'].get_dict()['POAV_cm^3/g']
        try:
            result_dict[
                'number_blocking_spheres'] = self.ctx.number_blocking_spheres
        except AttributeError:
            self.report('No blocked pockets found.')
            pass

        # RASPA loading
        try:
            result_dict['pressure_pa'] = self.ctx.pressure
            result_dict[
                'conversion_factor_molec_uc_to_cm3stp_cm3'] = self.ctx.raspa_loading[
                    "component_0"].get_dict(
                    )['conversion_factor_molec_uc_to_cm3stp_cm3']
            result_dict[
                'conversion_factor_molec_uc_to_gr_gr'] = self.ctx.raspa_loading[
                    "component_0"].get_dict(
                    )['conversion_factor_molec_uc_to_gr_gr']
            result_dict[
                'conversion_factor_molec_uc_to_mol_kg'] = self.ctx.raspa_loading[
                    "component_0"].get_dict(
                    )['conversion_factor_molec_uc_to_mol_kg']

            result_dict['rdfs'] = self.ctx.rdfs
            result_dict['mc_statistics'] = self.ctx.mc_statistics
            result_dict['warnings'] = self.ctx.raspa_warnings

            result_dict['loading_averages'] = self.ctx.loading
            result_dict['loading_dev'] = self.ctx.loading_dev
            result_dict[
                'enthalpy_of_adsorption'] = self.ctx.enthalpy_of_adsorption
            result_dict[
                'enthalpy_of_adsorption_dev'] = self.ctx.enthalpy_of_adsorption_dev

            result_dict[
                'ads_ads_coulomb_energy_average'] = self.ctx.ads_ads_coulomb_energy_average
            result_dict[
                'ads_ads_coulomb_energy_dev'] = self.ctx.ads_ads_coulomb_energy_dev
            result_dict[
                'ads_ads_total_energy_average'] = self.ctx.ads_ads_total_energy_average
            result_dict[
                'ads_ads_total_energy_dev'] = self.ctx.ads_ads_total_energy_dev
            result_dict[
                'ads_ads_vdw_energy_average'] = self.ctx.ads_ads_vdw_energy_average
            result_dict[
                'ads_ads_vdw_energy_dev'] = self.ctx.ads_ads_vdw_energy_dev

            result_dict[
                'host_ads_coulomb_energy_average'] = self.ctx.host_ads_coulomb_energy_average
            result_dict[
                'host_ads_coulomb_energy_dev'] = self.ctx.host_ads_coulomb_energy_dev
            result_dict[
                'host_ads_total_energy_average'] = self.ctx.host_ads_total_energy_average
            result_dict[
                'host_ads_total_energy_dev'] = self.ctx.host_ads_total_energy_dev
            result_dict[
                'host_ads_vdw_energy_average'] = self.ctx.host_ads_vdw_energy_average
            result_dict[
                'host_ads_vdw_energy_dev'] = self.ctx.host_ads_vdw_energy_dev
            result_dict['total_energy_average'] = self.ctx.total_energy_average
            result_dict['total_energy_dev'] = self.ctx.total_energy_dev

        except AttributeError:
            self.report(
                'Problems with returning the results dictionary for the RASPA part.'
            )
            pass

        self.out("results", ParameterData(dict=result_dict).store())
        self.out('blocking_spheres', self.ctx.zeopp['block'])
        self.report("Workchain <{}> completed successfully".format(
            self.calc.pk))

        return
