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


### gcmc_md_monitor_rdf (development branch)
In development. 

## Notes
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
  
## Settings for the study 

The folder `files_4_study` contains the runscript, the structures with charges and the
force field definitions. 


| Value                     | Setting                   |
| --------------------------| --------------------------|
| systems                   | al-fumarate, mil-160, uio-66, mil-125-nh2 |
| probe radius / A          | 3.1589/2.                 |
| force field               | UFF with all interactions |
| water model               | TIP4P 2005                | 
| partial charge derivation method | DDEC / EqEq (for MIL-125-NH2) | 
| number repeats            | 30                        | 
| number initialization cycles | 20 000                 | 
| cycles first GCMC         | 5 000                     |
| cycles short GCMC         | 1 000                     | 
| temperature GCMC / K      | 298.0                     | 
| temperature MD  / K       | 298.0                     | 
| timestep MD / fs          | 0.0005                    |
| cycles MD                 | 15 000                    |
| pressures /  Pa           | 00.0001E5, 00.001E5, 00.002E5, 00.004E5, 00.006E5, 00.008E5, 00.011E5, 00.014E5, 00.016E5, 00.018E5, 00.021E5, 00.023E5, 00.026E5, 00.0298E5, 00.036E5, 00.04E5|
| cutoff / A                | 13                        |
| tail-correction           | yes, since RASPA uses switching potential there is no problem in MD |

In total this means we run 5 000 * 20 + 1 000 * 30 * 20 = 700 000 MC steps. 
And we run 30 * 0.0005 fs * 15 000 * 20 = 4.5 ps of MD trajectory.