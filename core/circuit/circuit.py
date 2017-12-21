"""Basic neural mass model class plus derivations of it.
"""

import numpy as np
import matplotlib.pyplot as plt
from networkx import MultiDiGraph

from core.population import Population, PlasticPopulation, \
    JansenRitPyramidalCells, JansenRitExcitatoryInterneurons, JansenRitInhibitoryInterneurons
from core.utility import interpolate_array, check_nones
from typing import List, Optional, Dict, Union, TypeVar
PopulationLike = TypeVar('PopulationLike', bound=Population, covariant=True)


__author__ = "Richard Gast, Daniel Rose"
__status__ = "Development"

# TODO: Implement extrinsic modulatory mechanisms (see modulatory input parameter at population level)


class Circuit(object):
    """Base circuit class.

    Initializes a number of (delay-) coupled populations (neural masses) that are each characterized by a number of
    synapses and a single axon.

    Parameters
    ----------
    populations
        List of population instances. Need to have same simulation step-size.
    connectivity
        3D array (n_populations x n_populations x n_synapses) with each entry representing the average number of
        synaptic contacts between two populations via a given synapse type. 1. dimension are the receiving populations,
        2. dimension are the sending populations.
    delays
        2D array (n_populations x n_populations) with each entry representing the information transfer delay between the
        respective populations [unit = s].
    step_size
        Simulation step-size [unit = s] (default = 5e-4).

    Attributes
    ----------
    populations
        See description of parameter `populations`
    population_firing_rates
        2D array with the firing rates of all populations (1.dim) at the current and previous time-step (2.dim)
        [unit = 1/s].
    C
        See description of parameter `connectivity`.
    D
        See description of parameter `delays`.
    step_size
        See description of parameter `step_size`.
    N
        Number of populations in circuit.
    n_synapses
        Number of synapse types in circuit.
    t
        Current time the circuit lives at [unit = s].
    active_synapses
        2D boolean array indicating which synapses (2.dim) exist on which population (1.dim).

    """

    def __init__(self,
                 populations: List[Union[Population, PlasticPopulation]],
                 connectivity: np.ndarray,
                 delays: np.ndarray,
                 step_size: float=5e-4
                 ) -> None:
        """Instantiates population circuit object.
        """

        ##########################
        # check input parameters #
        ##########################

        # attribute dimensions
        if len(populations) != connectivity.shape[0] or len(populations) != connectivity.shape[1]:
            raise AttributeError('First and second dimension of connectivity matrix must equal the number of '
                                 'populations. See parameter docstrings for further explanation.')
        if len(populations) != delays.shape[0] or len(populations) != delays.shape[1]:
            raise AttributeError('First and second dimension of delay matrix must equal the number of populations. '
                                 'See parameter docstrings for further explanation.')

        # attribute values
        if np.sum(delays < 0.) > 0 or step_size < 0.:
            raise ValueError('Time constants (delays, step_size) cannot be negative. See parameter docstrings for '
                             'further explanation.')

        ##########################
        # set circuit attributes #
        ##########################

        # circuit properties
        self.step_size = step_size
        self.N = len(populations)
        self.n_synapses = connectivity.shape[2]
        self.t = 0.
        self.active_synapses = list()

        # circuit structure
        self.populations = populations
        self.C = connectivity
        self.D = delays

        # collector variables
        self.synaptic_input = np.zeros((self.N + 1, self.n_synapses))

        # population specific properties
        for i in range(self.N):

            # make sure state variable history will be saved on population
            self.populations[i].store_state_variables = True

            # check and extract synapses that exist at respective population
            idx = np.where(np.sum(connectivity[i, :, :].squeeze(), axis=0) != 0)[0]
            self.active_synapses.append([idx[i] for i in range(len(idx))])

            # check whether max_population_delay has changed
            if np.max(delays[i, :]) > self.populations[i].max_population_delay:
                self.populations[i].max_population_delay = np.max(delays[i, :])

            # TODO: make sure that population step-size corresponds to circuit step-size

        ########################
        # create network graph #
        ########################

        # create empty directed multi-graph
        self.network_graph = MultiDiGraph()

        # add population as network node
        for i in range(self.N):
            self.network_graph.add_node(i, data=self.populations[i])

        # add connections to other network nodes as edges
        for i in range(self.N):

            new_synapses = list()

            for k2, k in enumerate(self.active_synapses[i]):

                    for j in range(self.N):

                        if self.C[i, j, k] > 0:

                            if isinstance(self.populations[i], PlasticPopulation) and \
                                    self.populations[i].plastic_synapses[k]:

                                # add synapse copy to population
                                plasticity_dict = {'tau_depression': self.populations[i].tau_depression[k],
                                                   'tau_recycle': self.populations[i].tau_recycle[k]}
                                self.populations[i].add_synapse(synapse_idx=k, plasticity_taus=plasticity_dict,
                                                                max_firing_rate=self.populations[j].axon.
                                                                transfer_function_args['max_firing_rate'] *
                                                                                self.C[i, j, k])
                                new_synapses.append(self.populations[i].n_synapses - 1)

                                # create new edge
                                self.network_graph.add_edge(j, i,
                                                            weight=float(self.C[i, j, k]),
                                                            delay=int(self.D[i, j]),
                                                            synapse_index=new_synapses[-1])

                            else:

                                # create new edge
                                self.network_graph.add_edge(j, i,
                                                            weight=float(self.C[i, j, k]),
                                                            delay=int(self.D[i, j]),
                                                            synapse_index=k2)

            self.active_synapses[i] += new_synapses

    def run(self, synaptic_inputs: np.ndarray,
            simulation_time: float,
            extrinsic_current: Optional[np.ndarray]=None,
            extrinsic_modulation: Optional[list]=None,
            verbose: bool=False) -> None:
        """Simulates circuit behavior over time.

        Parameters
        ----------
        synaptic_inputs
            3D array (n_timesteps x n_populations x n_synapses) of synaptic input [unit = 1/s].
        simulation_time
            Total simulation time [unit = s].
        extrinsic_current
            2D array (n_timesteps x n_populations) of current extrinsically applied to the populations [unit = A].
        extrinsic_modulation
            List (with n_populations entries) of vectors with extrinsic modulatory influences on each synapse of a
            population.
        verbose
            If true, simulation progress will be printed to console.

        """
        ##########################
        # check input parameters #
        ##########################

        # simulation time
        if simulation_time < 0.:
            raise ValueError('Simulation time cannot be negative.')
        simulation_time_steps = int(simulation_time/self.step_size)

        # synaptic inputs
        if synaptic_inputs.shape[0] != simulation_time_steps:
            raise AttributeError('First dimension of synaptic input has to match the number of simulation time steps!')
        if synaptic_inputs.shape[1] != self.N:
            raise AttributeError('Second dimension of synaptic input has to match the number of populations in the '
                                 'circuit!')
        if synaptic_inputs.shape[2] != self.n_synapses:
            raise AttributeError('Third dimension of synaptic input has to match the number of synapse types in the '
                                 'circuit!')

        # extrinsic currents
        if not extrinsic_current:
            extrinsic_current = np.zeros((simulation_time_steps, self.N))
        else:
            if extrinsic_current.shape[0] != simulation_time_steps:
                raise AttributeError('First dimension of extrinsic current has to match the number of simulation time '
                                     'steps!')
            if extrinsic_current.shape[1] != self.N:
                raise AttributeError('Second dimension of extrinsic current has to match the number of populations!')

        # extrinsic modulation
        if not extrinsic_modulation:
            extrinsic_modulation = np.ones((simulation_time_steps, self.N)).tolist()
        else:
            if len(extrinsic_modulation) != simulation_time_steps:
                raise AttributeError('First dimension of extrinsic modulation has to match the number of simulation '
                                     'time steps!')
            if len(extrinsic_current[0]) != self.N:
                raise AttributeError('Second dimension of extrinsic current has to match the number of populations!')

        ####################
        # simulate network #
        ####################

        for n in range(simulation_time_steps):

            # pass information through circuit
            self.pass_through_circuit()

            # update all population states
            self.update_population_states(synaptic_inputs[n],
                                          extrinsic_current[n],
                                          extrinsic_modulation[n])

            # display simulation progress
            if verbose and (n == 0 or (n % (simulation_time_steps // 10)) == 0):
                print('simulation progress: ', "%.2f" % ((self.t / simulation_time) * 100.), ' %')

            # update time-variant variables
            self.t += self.step_size

    def update_population_states(self,
                                 synaptic_inputs: np.ndarray,
                                 extrinsic_current: np.ndarray,
                                 extrinsic_modulation: np.ndarray,
                                 ) -> None:
        """Updates states of all populations

        Parameters
        ----------
        synaptic_inputs
        extrinsic_current
        extrinsic_modulation

        """

        for i in range(self.N):
            self.populations[i].state_update(synaptic_input=synaptic_inputs[i, self.active_synapses[i]
                                                                               [0:synaptic_inputs.shape[1]]],
                                             extrinsic_current=extrinsic_current[i],
                                             extrinsic_synaptic_modulation=extrinsic_modulation[i])

    def pass_through_circuit(self):
        """Passes current population firing rates through circuit.
        """

        for i in range(self.N):
            self.project_to_populations(i)

    def project_to_populations(self, pop: int) -> None:
        """Projects output of given population to the other circuit populations its connected to.

        Parameters
        ----------
        pop
            Index of population where projection origins.

        """

        # extract network connections
        connected_pops = self.network_graph[pop]

        # loop over connections of node
        for target_pop in connected_pops:

            # loop over existing connections between node and target node
            for conn_idx in connected_pops[target_pop]:

                # transfer input to target node
                self.network_graph.node[target_pop]['data'].synaptic_input[
                    self.network_graph.node[target_pop]['data'].current_input_idx +
                    connected_pops[target_pop][conn_idx]['delay'],
                    connected_pops[target_pop][conn_idx]['synapse_index']] += \
                    self.network_graph.node[pop]['data'].current_firing_rate * \
                    connected_pops[target_pop][conn_idx]['weight']

    def get_population_states(self, state_variable_idx: int, time_window: Optional[List[float]]=None) -> np.ndarray:
        """Extracts specified state variable from populations and puts them into matrix.

        Parameters
        ----------
        state_variable_idx
            Index of state variable that is to be extracted.
        time_window
            Start and end of time window for which to extract the state variables [unit = s].

        Returns
        -------
        np.ndarray
            2D array (n_timesteps x n_populations) of state variable entries.

        """

        ##########################
        # check input parameters #
        ##########################

        if state_variable_idx < 0:
            raise ValueError('Index cannot be negative.')
        if time_window and any(time_window) < 0:
            raise ValueError('Time constants cannot be negative.')

        ############################################
        # extract state variables from populations #
        ############################################

        # get states from populations for all time-steps
        states = np.array([np.array(p.state_variables)[:, state_variable_idx] for p in self.populations]).T

        # reduce states to time-window
        if time_window:
            states = states[int(time_window[0]/self.step_size):int(time_window[1]/self.step_size), :]

        return states

    def plot_population_states(self, population_idx: Optional[List[int]]=None, state_idx: Optional[int] = 0,
                               time_window: Optional[List[float]]=None, create_plot: Optional[bool]=True,
                               axes=None) -> object:
        """Creates figure with population states over time.

        Parameters
        ----------
        population_idx
            Index of populations for which to plot states over time.
        state_idx
            State variable index.
        time_window
            Start and end time point for which to plot population states.
        create_plot
            If true, plot will be shown.
        axes
            Optional axis handle.

        Returns
        -------
        object
            Axis handle.

        """

        #########################
        # get population states #
        #########################

        population_states = self.get_population_states(state_idx, time_window)

        ########################
        # apply population idx #
        ########################

        if population_idx is None:
            population_idx = range(self.N)

        population_states = population_states[:, population_idx]

        #####################
        # apply time window #
        #####################

        if time_window is None:
            time_window = np.array([0, population_states.shape[1]])
        time_window = np.array(time_window / self.step_size, dtype=int)

        population_states = population_states[time_window[0]:time_window[1], :]

        ####################################
        # plot population states over time #
        ####################################

        if axes is None:
            fig, axes = plt.subplots(num='Population States')
        # plt.hold('on')  # deprecated in matplotlib version >2.0

        legend_labels = []
        for i in population_idx:
            axes.plot(population_states[:, i])
            legend_labels.append(self.populations[i].label)

        # plt.hold('off')  # deprecated in matplotlib version >2.0
        plt.legend(legend_labels)
        axes.set_ylabel('membrane potential [V]')
        axes.set_xlabel('time-steps')

        if create_plot:
            fig.show()

        return axes


class CircuitFromScratch(Circuit):
    """Circuit class that requires information about each synapse/axon in the circuit to be build.

    Parameters
    ----------
    synapses
        List of synapse types that exist in circuit (n_synapses strings).
    axons
        List of axon types that exist on each population (n_populations strings).
    connectivity
        See docstring for parameter `connectivity` of :class:`Circuit`.
    delays
        See docstring for parameter `delays` of :class:`Circuit`.
    step_size
        See docstring for parameter `step_size` of :class:`Circuit`.
    synapse_params
        List of dictionaries (with n_synapses entries) that include name-value pairs for each synapse parameter.
    max_synaptic_delay
        Maximum time after which input can still affect synapses [unit = s].
    axon_params
        List of dictionaries (with n_populations entries) that include name-value pairs for each axon parameter.
    membrane_capacitance
        Population membrane capacitance [unit = q/S].
    tau_leak
        Time-constant of population leak current [unit = s].
    resting_potential
        Population resting-state membrane potential [unit = V].
    init_states
        2D array containing the initial values for each state variable (2.dim) of each population (1.dim).
    population_labels
        Labels of populations.
    plastic_populations
        If true, populations will be instances of :class:`PlasticPopulation`


    See Also
    --------
    :class:`Circuit`: Detailed explanation of attributes and methods on circuit.

    """
    def __init__(self,
                 connectivity: np.ndarray,
                 delays: Optional[np.ndarray] = None,
                 step_size: Optional[float] = 5e-4,
                 synapses: Optional[List[str]]=None,
                 axons: Optional[Union[str, List[str]]]=None,
                 synapse_params: Optional[List[dict]]=None,
                 max_synaptic_delay: Optional[Union[float, List[float]]]=0.05,
                 synaptic_modulation_direction: Optional[List[List[np.ndarray]]]=None,
                 synapse_class: Union[str, List[str]] = 'DoubleExponentialSynapse',
                 axon_params: Optional[List[dict]]=None,
                 axon_class: Union[str, List[str]] = 'SigmoidAxon',
                 membrane_capacitance: Optional[Union[float, List[float]]]=1e-12,
                 tau_leak: Optional[Union[float, List[float]]]=0.016,
                 resting_potential: Optional[Union[float, List[float]]]=-0.075,
                 init_states: Optional[np.ndarray]=0.,
                 population_labels: Optional[List[str]]=None,
                 plastic_populations: bool=False
                 ) -> None:
        """Instantiates circuit from synapse/axon types and parameters.
        """

        ##########################
        # check input parameters #
        ##########################

        # check whether axon/synapse information was given
        if not synapses and not synapse_params:
            raise AttributeError('Either synapses or synapse_params have to be passed!')
        if not axons and not axon_params:
            raise AttributeError('Either axons or axon_params have to be passed!')

        # check attribute dimensions
        n_synapses = len(synapses) if synapses else len(synapse_params)
        if n_synapses != connectivity.shape[2]:
            raise AttributeError('Number of synapses needs to match the third dimension of connectivity. See docstrings'
                                 'for further explanation.')
        n_axons = len(axons) if axons else len(axon_params)
        if n_axons != connectivity.shape[0]:
            raise AttributeError('Number of axons needs to match the first dimension of connectivity. See docstrings'
                                 'for further explanation.')

        ###########################
        # instantiate populations #
        ###########################

        N = connectivity.shape[0]

        # check information transmission delay
        if not delays:
            delays = np.zeros((N, N), dtype=int)
        else:
            delays = np.array(delays / step_size, dtype=int)

        # set maximum transfer delay for each population
        max_population_delay = np.max(delays, axis=1)

        # make float variables iterable
        if type(init_states) is float:
            init_states = np.zeros(N) + init_states
        if type(max_synaptic_delay) is float:
            max_synaptic_delay = np.zeros(N) + max_synaptic_delay
        if type(tau_leak) is float:
            tau_leak = np.zeros(N) + tau_leak
        if type(resting_potential) is float:
            resting_potential = np.zeros(N) + resting_potential
        if type(membrane_capacitance) is float:
            membrane_capacitance = np.zeros(N) + membrane_capacitance

        # make None and str variables iterable
        synapses = check_nones(synapses, n_synapses)
        synapse_params = check_nones(synapse_params, n_synapses)
        axons = check_nones(axons, N)
        axon_params = check_nones(axon_params, N)
        synaptic_modulation_direction = check_nones(synaptic_modulation_direction, N)
        if not population_labels:
            population_labels = ['Custom' for i in range(N)]
        if type(synapse_class) is str:
            synapse_class = [synapse_class for i in range(n_synapses)]
        if type(axon_class) is str:
            axon_class = [axon_class for i in range(N)]

        # instantiate each population
        populations = list()
        for i in range(connectivity.shape[0]):

            # check and extract synapses that exist at respective population
            idx = (np.sum(connectivity[i, :, :], axis=0) != 0).squeeze()
            idx = np.asarray(idx.nonzero(), dtype=int)
            if len(idx) == 1:
                idx = idx[0]
            synapses_tmp = [synapses[j] for j in idx]
            synapse_params_tmp = [synapse_params[j] for j in idx]
            synapse_class_tmp = [synapse_class[j] for j in idx]

            # pass parameters to function that initializes the population
            if plastic_populations:
                populations.append(PlasticPopulation(synapses=synapses_tmp,
                                                     axon=axons[i],
                                                     init_state=init_states[i],
                                                     step_size=step_size,
                                                     max_synaptic_delay=max_synaptic_delay[i],
                                                     synaptic_modulation_direction=synaptic_modulation_direction[i],
                                                     tau_leak=tau_leak[i],
                                                     resting_potential=resting_potential[i],
                                                     membrane_capacitance=membrane_capacitance[i],
                                                     max_population_delay=max_population_delay[i],
                                                     axon_params=axon_params[i],
                                                     synapse_params=synapse_params_tmp,
                                                     synapse_class=synapse_class_tmp,
                                                     axon_class=axon_class[i],
                                                     label=population_labels[i]))
            else:
                populations.append(Population(synapses=synapses_tmp,
                                              axon=axons[i],
                                              init_state=init_states[i],
                                              step_size=step_size,
                                              max_synaptic_delay=max_synaptic_delay[i],
                                              synaptic_modulation_direction=synaptic_modulation_direction[i],
                                              tau_leak=tau_leak[i],
                                              resting_potential=resting_potential[i],
                                              membrane_capacitance=membrane_capacitance[i],
                                              max_population_delay=max_population_delay[i],
                                              axon_params=axon_params[i],
                                              synapse_params=synapse_params_tmp,
                                              synapse_class=synapse_class_tmp,
                                              axon_class=axon_class[i],
                                              label=population_labels[i]))

        ###################
        # call super init #
        ###################

        super().__init__(populations=populations,
                         connectivity=connectivity,
                         delays=delays,
                         step_size=step_size)


class CircuitFromPopulations(Circuit):
    """Circuit class that requires information about each population in the circuit to be build.

    Parameters
    ----------
    population_types
        List of population types (n_populations strings).
    connectivity
        See docstring for parameter `connectivity` of :class:`Circuit`.
    delays
        See docstring for parameter `delays` of :class:`Circuit`.
    step_size
        See docstring for parameter `step_size` of :class:`Circuit`.
    max_synaptic_delay
        Maximum time after which input can still affect synapses [unit = s].
    membrane_capacitance
        Population membrane capacitance [unit = q/S].
    tau_leak
        Time-constant of population leak current [unit = s].
    resting_potential
        Population resting-state membrane potential [unit = V].
    init_states
        2D array containing the initial values for each state variable (2.dim) of each population (1.dim).

    See Also
    --------
    :class:`Circuit`: Detailed explanation of attributes and methods on circuit.

    """
    def __init__(self,
                 population_types: List[str],
                 connectivity: np.ndarray,
                 delays: Optional[np.ndarray] = None,
                 step_size: Optional[float] = 5e-4,
                 max_synaptic_delay: Optional[Union[float, List[float]]] = 0.05,
                 synaptic_modulation_direction: Optional[List[List[np.ndarray]]]=None,
                 membrane_capacitance: Optional[Union[float, List[float]]]=1e-12,
                 tau_leak: Optional[Union[float, List[float]]]=0.016,
                 resting_potential: Optional[Union[float, List[float]]]=-0.075,
                 init_states: Optional[np.ndarray]=0.,
                 population_labels: Optional[List[str]]=None) -> None:
        """Instantiates circuit from population types and parameters.
        """

        ##########################
        # check input parameters #
        ##########################

        # attribute dimensions
        if len(population_types) != connectivity.shape[0]:
            raise AttributeError('One population type per population in circuit has to be passed. See parameter '
                                 'docstring for further information.')

        ###########################
        # instantiate populations #
        ###########################

        N = len(population_types)

        # check information transmission delay
        if not delays:
            delays = np.zeros((N, N), dtype=int)
        else:
            delays = np.array(delays / step_size, dtype=int)

        # set maximum transfer delay for each population
        max_population_delay = np.max(delays, axis=1)

        # make float variables iterable
        if type(init_states) is float:
            init_states = np.zeros(N) + init_states
        if type(max_synaptic_delay) is float:
            max_synaptic_delay = np.zeros(N) + max_synaptic_delay
        if type(tau_leak) is float:
            tau_leak = np.zeros(N) + tau_leak
        if type(resting_potential) is float:
            resting_potential = np.zeros(N) + resting_potential
        if type(membrane_capacitance) is float:
            membrane_capacitance = np.zeros(N) + membrane_capacitance

        # make None variables iterable
        synaptic_modulation_direction = check_nones(synaptic_modulation_direction, N)
        if not population_labels:
            population_labels = ['Custom' for i in range(N)]

        # instantiate each population
        populations = list()
        for i in range(N):

            if population_types[i] == 'JansenRitPyramidalCells':
                pop = JansenRitPyramidalCells(init_state=init_states[i],
                                              step_size=step_size,
                                              max_synaptic_delay=max_synaptic_delay[i],
                                              synaptic_modulation_direction=synaptic_modulation_direction[i],
                                              tau_leak=tau_leak[i],
                                              membrane_capacitance=membrane_capacitance[i],
                                              resting_potential=resting_potential[i],
                                              max_population_delay=max_population_delay[i],
                                              label=population_labels[i])

            elif population_types[i] == 'JansenRitExcitatoryInterneurons':
                pop = JansenRitExcitatoryInterneurons(init_state=init_states[i],
                                                      step_size=step_size,
                                                      max_synaptic_delay=max_synaptic_delay[i],
                                                      synaptic_modulation_direction=synaptic_modulation_direction[i],
                                                      tau_leak=tau_leak[i],
                                                      membrane_capacitance=membrane_capacitance[i],
                                                      resting_potential=resting_potential[i],
                                                      max_population_delay=max_population_delay[i],
                                                      label=population_labels[i])

            elif population_types[i] == 'JansenRitInhibitoryInterneurons':
                pop = JansenRitInhibitoryInterneurons(init_state=init_states[i],
                                                      step_size=step_size,
                                                      max_synaptic_delay=max_synaptic_delay[i],
                                                      synaptic_modulation_direction=synaptic_modulation_direction[i],
                                                      tau_leak=tau_leak[i],
                                                      membrane_capacitance=membrane_capacitance[i],
                                                      resting_potential=resting_potential[i],
                                                      max_population_delay=max_population_delay[i],
                                                      label=population_labels[i])

            else:
                raise ValueError('Population type does not exist. See docstring of parameter `population_types` for '
                                 'further information.')

            populations.append(pop)

        ###################
        # call super init #
        ###################

        super().__init__(populations=populations,
                         connectivity=connectivity,
                         delays=delays,
                         step_size=step_size)


class CircuitFromCircuit(Circuit):
    """Circuit class that builds higher-level circuit from multiple lower-level circuits.

        Parameters
        ----------
        circuits
            List of circuit instances.
        connectivity
            See docstring for parameter `connectivity` of :class:`Circuit`.
        delays
            See docstring for parameter `delays` of :class:`Circuit`.
        input_populations
            3D list of indices for the input populations (3.dim) of each pair-wise connection (1. + 2.dim).
        output_populations
            2D array of indices for the output population of each pair-wise connection.
        circuit_labels
            List of strings with circuit labels.

        See Also
        --------
        :class:`Circuit`: Detailed explanation of attributes and methods on circuit.

        """

    def __init__(self,
                 circuits: List[Circuit],
                 connectivity: np.ndarray,
                 delays: Optional[np.ndarray]=None,
                 input_populations: Optional[np.ndarray]=None,
                 output_populations: Optional[np.ndarray]=None,
                 circuit_labels: Optional[List[str]]=None) -> None:
        """Instantiates circuit from population types and parameters.
        """

        ##########################
        # check input parameters #
        ##########################

        # attribute dimensions
        if len(circuits) != connectivity.shape[0] or len(circuits) != connectivity.shape[1]:
            raise AttributeError('First and second dimension of connectivity need to match the number of circuits. '
                                 'See parameter docstring for further information.')
        if delays is not None and (len(circuits) != delays.shape[0] or len(circuits) != delays.shape[1]):
            raise AttributeError('First and second dimension of delays need to match the number of circuits. '
                                 'See parameter docstring for further information.')

        ######################################
        # fetch important circuit attributes #
        ######################################

        n_circuits = len(circuits)

        if not circuit_labels:
            circuit_labels = ['' for i in range(n_circuits)]

        # set delays
        if delays is None:
            delays = np.zeros((n_circuits, n_circuits), dtype=int)
        else:
            delays = np.array(delays / circuits[0].step_size, dtype=int)

        # set maximum transfer delay for each population
        max_population_delay = np.max(delays, axis=1)

        # initialize stuff
        n_populations = np.zeros(n_circuits+1, dtype=int)
        connectivity_coll = list()
        delays_coll = list()
        populations = list()
        n_synapses = np.zeros(n_circuits, dtype=int)

        # loop over circuits
        for i in range(n_circuits):

            # collect population count
            n_populations[i+1] = n_populations[i] + circuits[i].N

            # collect connectivity matrix
            connectivity_tmp = circuits[i].C
            n_synapses_diff = connectivity.shape[2] - connectivity_tmp.shape[2]
            if n_synapses_diff > 0:
                connectivity_tmp = np.append(connectivity_tmp, np.zeros((circuits[i].N, circuits[i].N)), axis=2)
            connectivity_coll.append(connectivity_tmp)

            # collect delay matric
            delays_coll.append(circuits[i].D)

            # collect number of synapses
            n_synapses[i] = circuits[i].n_synapses

            # collect populations
            for pop in circuits[i].populations:

                # update population label
                pop.label = circuit_labels[i] + '_' + pop.label

                # update population delay
                pop.synaptic_input = np.zeros((int((len(pop.synapses[0].synaptic_kernel) + max_population_delay[i])),
                                               len(pop.synapses)))

                # add population
                populations.append(pop)

        # check whether synapse dimensions match
        if any(n_synapses) > connectivity.shape[2]:
            raise AttributeError('Cannot connect circuits that have more synapses than outer connectivity matrix!')

        ###########################################
        # build new connectivity and delay matrix #
        ###########################################

        # set input populations
        if not input_populations:
            input_populations = np.zeros((n_circuits, n_circuits, 1), dtype=int).tolist()

        # set output populations
        if not output_populations:
            output_populations = np.zeros((n_circuits, n_circuits), dtype=int)

        # initialize stuff
        connectivity_new = np.zeros((n_populations[-1], n_populations[-1], connectivity.shape[2]))
        delays_new = np.zeros((n_populations[-1], n_populations[-1]), dtype=int)

        # loop over all circuits
        for i in range(n_circuits):

            # set intra-circuit connectivity of circuit i
            connectivity_new[n_populations[i]:n_populations[i+1], n_populations[i]:n_populations[i+1], :] = \
                connectivity_coll[i]

            # set intra-circuit delays of circuit i
            delays_new[n_populations[i]:n_populations[i+1], n_populations[i]:n_populations[i+1]] = delays_coll[i]

            # loop again over all circuits
            for j in range(n_circuits):

                # for other circuits
                if i != j:

                    # loop over each input population in circuit i,j
                    for k in range(len(input_populations[i][j])):

                        # set inter-circuit connectivities
                        connectivity_new[n_populations[j]+input_populations[i][j][k],
                                         n_populations[i]+output_populations[i, j], :] = connectivity[i, j, :]

                        # set inter-circuit delays
                        delays_new[n_populations[j] + input_populations[i][j][k],
                                   n_populations[i] + output_populations[i, j]] = delays[i, j]

        ###################
        # call super init #
        ###################

        super().__init__(populations=populations,
                         connectivity=connectivity_new,
                         delays=delays_new,
                         step_size=circuits[0].step_size)


# def update_step_size(self, new_step_size, synaptic_inputs, update_threshold=1e-2, extrinsic_current=None,
#                      extrinsic_synaptic_modulation=None, idx=0, interpolation_type='linear'):
#     """
#     Updates the time-step size with which the network is simulated.
#
#     :param new_step_size: Scalar, indicates the new simulation step-size [unit = s].
#     :param synaptic_inputs: synaptic input array that needs to be interpolated.
#     :param update_threshold: If step-size ratio (old vs new) is larger than threshold, interpolations are initiated.
#     :param extrinsic_current: extrinsic current array that needs to be interpolated.
#     :param extrinsic_synaptic_modulation: synaptic modulation that needs to be interpolated.
#     :param idx: Can be used to interpolate arrays from this point on (int) (default = 0).
#     :param interpolation_type: character string, indicates the type of interpolation used for up-/down-sampling the
#            firing-rate look-up matrix (default = 'cubic').
#
#     :return interpolated synaptic input array.
#     """
#
#     ############################################
#     # check whether update has to be performed #
#     ############################################
#
#     step_size_ratio = np.max((self.step_size, new_step_size)) / np.min((self.step_size, new_step_size))
#
#     if np.abs(step_size_ratio - 1) > update_threshold and self.time_steps:
#
#         ##########################
#         # update step-size field #
#         ##########################
#
#         step_size_old = self.step_size
#         self.step_size = new_step_size
#
#         ##############################
#         # update firing rate loop-up #
#         ##############################
#
#         # get maximum delay in seconds
#         delay = np.max(np.array(self.D, dtype=int)) + self.step_size
#
#         # check whether update is necessary
#         step_diff = abs(int(delay/self.step_size) - int(delay/step_size_old))
#
#         if step_diff >= 1 and delay > self.step_size:
#
#             # perform interpolation of old firing rate look-up
#             self.firing_rates_lookup = interpolate_array(old_step_size=step_size_old,
#                                                          new_step_size=self.step_size,
#                                                          y=self.firing_rates_lookup,
#                                                          interpolation_type=interpolation_type,
#                                                          axis=1)
#
#         ###############################
#         # update all extrinsic inputs #
#         ###############################
#
#         # check whether update is necessary
#         net_input_time = synaptic_inputs[idx:, :, :].shape[0] * step_size_old
#
#         step_diff = abs(int(net_input_time/self.step_size) - int(net_input_time/step_size_old))
#
#         if step_diff >= 1:
#
#             # perform updates
#             synaptic_inputs = interpolate_array(old_step_size=step_size_old,
#                                                 new_step_size=self.step_size,
#                                                 y=synaptic_inputs[idx:, :, :],
#                                                 axis=0,
#                                                 interpolation_type=interpolation_type)
#
#             if extrinsic_current:
#
#                 extrinsic_current = interpolate_array(old_step_size=step_size_old,
#                                                       new_step_size=self.step_size,
#                                                       y=extrinsic_current[idx:, :],
#                                                       axis=0,
#                                                       interpolation_type=interpolation_type)
#
#             if extrinsic_synaptic_modulation:
#
#                 extrinsic_synaptic_modulation = interpolate_array(old_step_size=step_size_old,
#                                                                   new_step_size=self.step_size,
#                                                                   y=np.array(extrinsic_synaptic_modulation)[idx:, :],
#                                                                   axis=0,
#                                                                   interpolation_type=interpolation_type).tolist()
#
#     return synaptic_inputs, extrinsic_current, extrinsic_synaptic_modulation, 0