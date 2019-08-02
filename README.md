# water_isotherm_workchains

## Implemented workchains is AiiDA 1
### converge_loading_workchain


## Implemented workchains in AiiDA 1.x

## Notes

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
