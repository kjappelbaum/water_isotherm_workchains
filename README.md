# water_isotherm_workchains

## Implemented workchain
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

## Notes
- My development version of the RASPA plugin need to be used to retrieve statistics about the MC moves 
  and the RDFs
- The settings are not optimized but rather used for a "prove of concept"
- Make sure to expand the unitcells before you use the workchain. The workchain also implements
  the expansion using the orthogonal widths, but it is not tested, especially, I do not know how RASPA
  deals with the charge loop in this case. You can use Daniele Ongari's `manage_crystal` to do this. 
- If you do not want the RDF output to explode use `'RemoveAtomNumberCodeFromLabel': 'yes'`. The RASPA
  manual states that the charges are still used correctly and our tests show that this is indeed the case

## Usage
1. Read the notes 
2. Clean this repository   
  
