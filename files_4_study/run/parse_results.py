"""Get cifs from the multistage DFT workflow"""

import os
from glob import glob
from pathlib import Path
import click
import pandas as pd
import pickle
from ase.io import read, write
from aiida.engine import WorkChain
from aiida.orm import Dict
from aiida.orm.querybuilder import QueryBuilder
from aiida.plugins import DataFactory
from water_isotherm_workchains.utils.utils import slugify

CifData = DataFactory("cif")


def query_structure(structure_label):
    qb = QueryBuilder()
    qb.append(
        CifData, tag="inp_struct", filters={"label": structure_label}, project=["uuid"]
    )
    qb.append(
        WorkChain,
        filters={"label": "MultiCompIsothermWorkChain-watertest"},
        with_incoming="inp_struct",
        tag="wc",
        project=["uuid"],
    )
    qb.append(Dict, with_outgoing="wc", project=["uuid"])
    qb.append(Dict, with_incoming="wc", project=["uuid"])
    return qb.all()


def main():
    result_list = []
    for s in glob(
        "/home/kevin/Dropbox/Documents/uni/EPFL/master_thesis/water_isotherm_workchains/files_4_study/structures/*.cif"
    ):
        structure_label = slugify(Path(s).stem)
        results_list = query_structure(structure_label)

        print(structure_label)
        for results in results_list:
            result_dict = {}

            result_dict['name'] = structure_label

            input_dict = load_node(results[-2]).get_dict()
            output_dict = load_node(results[-1]).get_dict()

            result_dict.update(input_dict)
            result_dict.update(output_dict)
            result_dict['wc_uuid'] = results[1]
            result_list.append(result_dict)
            

    df = pd.DataFrame(result_list)
    print(df.head())
    df.to_pickle('results.pkl')


if __name__ == "__main__":
    main()
