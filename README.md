# water_isotherm_workchains

## workchains
- Base Workchain. Simply submits short GCMCs at a given pressure. Submission script loops over pressures.
- MC/MD mix workchain, implements:
	1. Starts GCMC run
	2. Retrieves Restart, renames (?) and uses it as a start for a MD
	3. Runs MD trajectory
	4. Retrieves Restart, renames and it uses it for a new GCMC (step 1) 
- All workchains retrieve also the RDFs. 
