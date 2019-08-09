#!/bin/bash
#SBATCH --no-requeue
#SBATCH --job-name="aiida-None"
#SBATCH --get-user-env
#SBATCH --output=_scheduler-stdout.txt
#SBATCH --error=_scheduler-stderr.txt
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --time=00:30:00


export RASPA_DIR=/home/kjablonk/RASPA/simulations/
export DYLD_LIBRARY_PATH=/home/kjablonk/RASPA/simulations/lib
export LD_LIBRARY_PATH=/home/kjablonk/RASPA/simulations/lib


'/home/kjablonk/RASPA/simulations/bin/simulate' 'simulation.input'   

 
