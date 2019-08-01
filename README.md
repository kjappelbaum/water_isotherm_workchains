# water_isotherm_workchains

## Implemented workchains in AiiDA 0.x
### gcmc_restart
A simple RASPA loading workchain with the following features:
* blocks inaccessible pockets
* performs on longer RASPA GCMC run with initialization in the beginning and then multiple
  shorter GCMC runs. This allows for two things:
  * it is easier to retrieve good statistics
  * it is easier to compare with the GCMC/MD workchain

### gcmc_md
A workchain that cycles between short MD trajectories and short GCMC runs with the intuition that in
some cases collective dynamics from MD is needed to 'disturb' a configuration where GCMC has a hard
time in inserting new particles.


### gcmc_md_monitor_rdf (development branch)
In development.


## Implemented workchains in AiiDA 1.x

## Notes
### AiiDA 0.x
- My development version of the RASPA plugin need to be used to retrieve statistics about the MC moves
  and the RDFs, you can install it with
  `pip install git+https://github.com/kjappelbaum/aiida-raspa.git@develop` (warning! this might case problems
  in your older workflows. You might consider creating a special enviornment)
- The settings are not optimized but rather used for a "prove of concept"
- Make sure to expand the unitcells before you use the workchain. The workchain also implements
  the expansion using the orthogonal widths, but it is not tested, especially, I do not know how RASPA
  deals with the charge loop in this case. You can use Daniele Ongari's `manage_crystal` to do this.
- If you do not want the RDF output to explode use `'RemoveAtomNumberCodeFromLabel': 'yes'`. The RASPA
  manual states that the charges are still used correctly and our tests show that this is indeed the case

## Usage
1. Read the notes
2. pip install the workflows with `pip install git+https://github.com/kjappelbaum/water_isotherm_workchains`   
3. restart the daemon `verdi daemon restart`

to use the examples it might be easier to
1. `git clone` the repository
2. `cd water_isotherm workchains & pip install .`

## Known issues
* The output out the workchain is comparatively large as we save all RDFs for all simulations
  this can lead to problems if you have limited memory and want to safe into the database (i.e. in a
  Virtual Quantum Mobile machine we had issues whereas we had no problems in a 'real' machine)
