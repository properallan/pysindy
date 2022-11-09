import inspect
import time
import warnings

import dysts.flows as flows
import numpy as np
from dysts.analysis import sample_initial_conditions
from matplotlib import pyplot as plt
from scipy.special import comb
from sklearn.linear_model import Lasso
from sklearn.metrics import mean_squared_error

import pysindy as ps

# Annoyingly requires the neurokit2 package - "pip install neurokit2"


def run_ensembling(
    systems_list,
    all_sols_train,
    all_t_train,
    test_trajectories,
    test_trajectories_t,
    dimension_list,
    best_threshold_values,
    alpha=1e-5,
    optimizer_max_iter=100,
    normalize_columns=True,
    n_models=20,
):

    n = test_trajectories[systems_list[0]].shape[0]
    num_trajectories = test_trajectories[systems_list[0]].shape[1]
    poly_library = ps.PolynomialLibrary(degree=4)
    num_attractors = len(systems_list)
    x_dot_pred = dict()

    # x_dot_test = np.zeros((n, num_attractors, num_trajectories))
    x_pred = dict()
    coef_lists = dict()

    for i, attractor_name in enumerate(systems_list):

        print(i, attractor_name)
        x_train = np.copy(all_sols_train[attractor_name])
        t_train = all_t_train[attractor_name]

        if dimension_list[i] == 3:
            input_names = ["x", "y", "z"]
        else:
            input_names = ["x", "y", "z", "w"]

        x_dot_pred[attractor_name] = np.zeros((n, num_trajectories, dimension_list[i]))
        x_pred[attractor_name] = np.zeros((n, num_trajectories, dimension_list[i]))

        optimizer = ps.STLSQ(
            threshold=best_threshold_values[attractor_name][0],
            alpha=alpha,
            max_iter=optimizer_max_iter,
            normalize_columns=normalize_columns,
            ridge_kw={"tol": 1e-10},
        )
        model = ps.SINDy(
            feature_library=poly_library,
            optimizer=optimizer,
            feature_names=input_names,
        )
        model.fit(x_train, t=t_train, quiet=True, ensemble=True, n_models=n_models)
        coef_list = np.array(model.coef_list)
        coef_lists[attractor_name] = coef_list

        # for j in range(n_models):
        # optimizer.coef_ = coef_list[j, :, :]
        optimizer.coef_ = np.median(coef_list, axis=0)

        for k in range(num_trajectories):
            x_test = test_trajectories[attractor_name][:, k, :]
            t_test = test_trajectories_t[attractor_name][:, k]
            # x_dot_pred[attractor_name][:, j, k, :] = model.predict(x_test)
            # x_pred[attractor_name][:, j, k, :] = model.simulate(x_test[0, :], t_test)
            x_dot_pred[attractor_name][:, k, :] = model.predict(x_test)
            x0 = (
                x_test[0, :]
                + (np.random.rand(x_test[0, :].shape[0]) - 0.5)
                * np.linalg.norm(x_test)
                / 100.0
            )
            x_pred[attractor_name][:, k, :] = model.simulate(
                x0, t_test, integrator="odeint"
            )
    return x_pred, x_dot_pred, coef_lists


def plot_coef_errors(
    all_sols_train,
    best_normalized_coef_errors,
    xdot_rmse_errors,
    best_threshold_values,
    scale_list,
    systems_list,
    normalize_columns=True,
):
    # Count up number of systems that can be successfully identified to 10% total coefficient error
    num_attractors = len(systems_list)
    coef_summary = np.zeros(num_attractors)
    for i, attractor_name in enumerate(all_sols_train):
        coef_summary[i] = best_normalized_coef_errors[attractor_name][0] < 0.1

    print(
        "# of dynamical systems that have < 10% coefficient error in the fit, ",
        "when , error * 100, % Gaussian noise is added to every trajectory point ",
        int(np.sum(coef_summary)),
        " / ",
        len(systems_list),
    )

    plt.figure(figsize=(20, 2))
    for i, attractor_name in enumerate(all_sols_train):
        plt.scatter(
            i,
            best_normalized_coef_errors[attractor_name][0],
            c="r",
            label="Avg. normalized coef errors",
        )
        plt.scatter(
            i,
            abs(np.array(xdot_rmse_errors[attractor_name])),
            c="g",
            label="Avg. RMSE errors",
        )
        plt.scatter(
            i, best_threshold_values[attractor_name], c="b", label="Avg. best threshold"
        )
    plt.grid(True)
    plt.yscale("log")
    plt.plot(
        np.linspace(-0.5, num_attractors + 1, num_attractors),
        0.1 * np.ones(num_attractors),
        "k--",
        label="10% error",
    )
    plt.legend(
        ["10% normalized error", "$E_{coef}$", "$E_{RMSE}$", "Optimal threshold"],
        framealpha=1.0,
        ncol=4,
        fontsize=13,
    )
    ax = plt.gca()
    plt.xticks(np.arange(num_attractors), rotation="vertical", fontsize=16)
    plt.xlim(-0.5, num_attractors + 1)
    systems_list_cleaned = []
    for i, system in enumerate(systems_list):
        if system == "GuckenheimerHolmes":
            systems_list_cleaned.append("GuckenHolmes")
        elif system == "NuclearQuadrupole":
            systems_list_cleaned.append("NuclearQuad")
        elif system == "RabinovichFabrikant":
            systems_list_cleaned.append("RabFabrikant")
        elif system == "KawczynskiStrizhak":
            systems_list_cleaned.append("KawcStrizhak")
        elif system == "RikitakeDynamo":
            systems_list_cleaned.append("RikiDynamo")
        elif system == "ShimizuMorioka":
            systems_list_cleaned.append("ShMorioka")
        elif system == "HindmarshRose":
            systems_list_cleaned.append("Hindmarsh")
        elif system == "RayleighBenard":
            systems_list_cleaned.append("RayBenard")
        else:
            systems_list_cleaned.append(system)
    ax.set_xticklabels(np.array(systems_list_cleaned))
    if normalize_columns:
        plt.ylim(1e-4, 1e4)
    else:
        plt.ylim(1e-4, 1e1)
    plt.yticks(fontsize=20)
    plt.savefig("model_summary_without_added_noise_Algo3.pdf")

    # Repeat the plot, but reorder things by the amount of scale separation
    scale_sort = np.argsort(scale_list)
    scale_list_sorted = np.sort(scale_list)
    systems_list_sorted = np.array(systems_list)[scale_sort]
    cerrs = []
    rmse_errs = []
    plt.figure(figsize=(20, 2))
    for i, attractor_name in enumerate(systems_list_sorted):
        plt.scatter(
            i,
            best_normalized_coef_errors[attractor_name][0],
            c="r",
            label="Avg. normalized coef errors",
        )
        plt.scatter(
            i,
            abs(np.array(xdot_rmse_errors[attractor_name])),
            c="g",
            label="Avg. RMSE errors",
        )
        rmse_errs.append(abs(np.array(xdot_rmse_errors[attractor_name]))[0])
        cerrs.append(best_normalized_coef_errors[attractor_name][0])

    print(scale_list_sorted, rmse_errs)
    plt.grid(True)
    plt.yscale("log")
    plt.plot(
        np.linspace(-0.5, num_attractors + 1, num_attractors),
        0.1 * np.ones(num_attractors),
        "k--",
        label="10% error",
    )
    plt.legend(
        ["10% normalized error", "$E_{coef}$"],
        framealpha=1.0,
        ncol=4,
        fontsize=13,
        loc="upper left",
    )
    ax = plt.gca()
    plt.xticks(np.arange(num_attractors), rotation="vertical", fontsize=16)
    plt.xlim(-0.5, num_attractors + 1)
    ax.set_xticklabels(np.array(systems_list_cleaned)[scale_sort])
    # plt.ylim(1e-4, 1e1)
    plt.yticks(fontsize=20)
    plt.savefig("model_summary_scaleSeparation_without_added_noise_Algo3.pdf")

    from scipy.stats import linregress

    slope, intercept, r_value, p_value, std_err = linregress(
        scale_list_sorted, np.log(rmse_errs)
    )
    print(slope, intercept, r_value, p_value, std_err)
    print("R^2 value = ", r_value**2)

    plt.figure(figsize=(20, 2))
    for i, attractor_name in enumerate(systems_list_sorted):
        plt.scatter(
            scale_list_sorted[i],
            best_normalized_coef_errors[attractor_name][0],
            c="r",
            label="Avg. normalized coef errors",
        )
        plt.scatter(
            scale_list_sorted[i],
            abs(np.array(xdot_rmse_errors[attractor_name])),
            c="g",
            label="Avg. RMSE errors",
        )
    plt.plot(scale_list_sorted, np.exp(slope * scale_list_sorted + intercept), "k")
    plt.yscale("log")
    plt.xscale("log")
    plt.grid(True)
    # plt.yscale('log')
    # plt.plot(np.linspace(-0.5, num_attractors + 1, num_attractors), 0.1 * np.ones(num_attractors), 'k--', label='10% error')
    plt.legend(
        ["Best linear feat", "$E_{coef}$"],
        loc="lower right",
        framealpha=1.0,
        ncol=4,
        fontsize=13,
    )
    ax = plt.gca()
    # plt.xticks(np.arange(num_attractors), rotation='vertical', fontsize=16)
    # plt.xlim(-0.5, num_attractors + 1)
    # ax.set_xticklabels(np.array(systems_list_cleaned)[scale_sort])
    # plt.ylim(1e-4, 1e1)
    plt.yticks(fontsize=20)
    plt.savefig("model_summary_scaleSeparation_without_added_noise.pdf")
    plt.show()


def plot_individual_coef_errors(
    all_sols_train,
    predicted_coefficients,
    true_coefficients,
    dimension_list,
    systems_list,
    models,
):
    poly_library = ps.PolynomialLibrary(degree=4)
    colors = ["r", "b", "g", "m"]
    labels = ["xdot", "ydot", "zdot", "wdot"]

    for i, system in enumerate(systems_list):
        x_train = all_sols_train[system]
        plt.figure(figsize=(20, 2))
        if dimension_list[i] == 3:
            feature_names = poly_library.fit(x_train).get_feature_names(["x", "y", "z"])
        else:
            feature_names = poly_library.fit(x_train).get_feature_names(
                ["x", "y", "z", "w"]
            )
        for k in range(dimension_list[i]):
            plt.grid(True)
            plt.scatter(
                feature_names,
                np.mean(np.array(predicted_coefficients[system])[:, k, :], 0),
                color=colors[k],
                label=labels[k],
                s=100,
            )
            plt.scatter(
                feature_names,
                np.array(true_coefficients[i][k, :]),
                color="k",
                label="True " + labels[k],
                s=50,
            )
        if dimension_list[i] == 3:
            plt.legend(loc="upper right", framealpha=1.0, ncol=6)
        else:
            plt.legend(loc="upper right", framealpha=1.0, ncol=8)
        plt.title(system)
        # plt.yscale('symlog', linthreshy=1e-3)
        plt.legend(loc="upper right", framealpha=1.0, ncol=6)
        print(system)
        models[i].print()


def load_data(
    systems_list,
    all_properties,
    n=200,
    pts_per_period=20,
    random_bump=False,
    include_transients=False,
    n_trajectories=1,
):
    all_sols_train = dict()
    all_sols_test = dict()
    all_t_train = dict()
    all_t_test = dict()

    for i, equation_name in enumerate(systems_list):
        eq = getattr(flows, equation_name)()
        all_sols_train[equation_name] = []
        all_sols_test[equation_name] = []
        all_t_train[equation_name] = []
        all_t_test[equation_name] = []
        print(i, eq)

        for j in range(n_trajectories):
            ic_train, ic_test = sample_initial_conditions(
                eq, 2, traj_length=1000, pts_per_period=30
            )

            # Kick it off the attractor by random bump with, at most, 1% of the norm of the IC
            if random_bump:
                print(ic_train)
                ic_train += (np.random.rand(len(ic_train)) - 0.5) * abs(ic_train) / 50
                ic_test += (np.random.rand(len(ic_test)) - 0.5) * abs(ic_test) / 50
                print(ic_train)

            # Sample at roughly the smallest time scale!!
            if include_transients:
                pts_per_period = int(1 / (all_properties[equation_name]["dt"] * 10))
                n = pts_per_period * 10  # sample 10 periods at the largest time scale

            eq.ic = ic_train
            t_sol, sol = eq.make_trajectory(
                n,
                pts_per_period=pts_per_period,
                resample=True,
                return_times=True,
                standardize=False,
            )
            all_sols_train[equation_name].append(sol)
            all_t_train[equation_name].append(t_sol)
            eq.ic = ic_test
            t_sol, sol = eq.make_trajectory(
                n,
                pts_per_period=pts_per_period,
                resample=True,
                return_times=True,
                standardize=False,
            )
            all_sols_test[equation_name].append(sol)
            all_t_test[equation_name].append(t_sol)
    return all_sols_train, all_t_train, all_sols_test, all_t_test


def make_test_trajectories(
    systems_list,
    all_properties,
    n=200,
    pts_per_period=20,
    random_bump=False,
    include_transients=False,
    approximate_center=0.0,  # approximate center of the attractor
    n_trajectories=20,
):
    num_attractors = len(systems_list)
    all_sols_test = dict()
    all_t_test = dict()

    for i, equation_name in enumerate(systems_list):

        dimension = all_properties[equation_name]["embedding_dimension"]
        if dimension == 3:
            input_names = ["x", "y", "z"]
        else:
            input_names = ["x", "y", "z", "w"]
        all_sols_test[equation_name] = np.zeros((n, n_trajectories, dimension))
        all_t_test[equation_name] = np.zeros((n, n_trajectories))

        eq = getattr(flows, equation_name)()
        print(i, eq)

        ic_test = sample_initial_conditions(
            eq, n_trajectories, traj_length=1000, pts_per_period=30
        )

        # Sample at roughly the smallest time scale!!
        if include_transients:
            pts_per_period = int(1 / (all_properties[equation_name]["dt"] * 10))
            n = pts_per_period * 10  # sample 10 periods at the largest time scale

        # Kick it off the attractor by random bump with, at most, 25% of the norm of the IC
        for j in range(n_trajectories):
            if random_bump:
                ic_test[j, :] += (
                    (np.random.rand(len(ic_test[j, :])) - 0.5) * abs(ic_test[j, :]) / 10
                )
            eq.ic = ic_test[j, :]
            t_sol, sol = eq.make_trajectory(
                n,
                pts_per_period=pts_per_period,
                resample=True,
                return_times=True,
                standardize=False,
            )
            all_sols_test[equation_name][:, j, :] = sol
            all_t_test[equation_name][:, j] = t_sol
    return all_sols_test, all_t_test


def normalized_RMSE(x_dot_true, x_dot_pred):
    return np.linalg.norm(x_dot_true - x_dot_pred, ord=2) / np.linalg.norm(
        x_dot_true, ord=2
    )


def total_coefficient_error_normalized(xi_true, xi_pred):
    return np.linalg.norm(xi_true - xi_pred, ord=2) / np.linalg.norm(xi_true, ord=2)


def total_mean_coefficient_error_normalized(xi_true, xi_pred):
    return np.mean(abs(xi_true - xi_pred) / abs(xi_true))


def coefficient_errors(xi_true, xi_pred):
    errors = np.zeros(xi_true.shape)
    for i in range(xi_true.shape[0]):
        for j in range(xi_true.shape[1]):
            if np.isclose(xi_true[i, j], 0.0):
                errors[i, j] = abs(xi_true[i, j] - xi_pred[i, j])
            else:
                errors[i, j] = abs(xi_true[i, j] - xi_pred[i, j]) / xi_true[i, j]
    return errors


def total_coefficient_error(xi_true, xi_pred):
    errors = np.zeros(xi_true.shape)
    for i in range(xi_true.shape[0]):
        for j in range(xi_true.shape[1]):
            errors[i, j] = xi_true[i, j] - xi_pred[i, j]
    return np.linalg.norm(errors, ord=2)


def success_rate(xi_true, xi_pred):
    print("to do")


# def stability_metric():


def Pareto_scan(
    systems_list,
    dimension_list,
    true_coefficients,
    all_sols_train,
    all_t_train,
    all_sols_test,
    all_t_test,
    coef_error_metric=False,
    l0_penalty=1e-5,
    normalize_columns=True,
    error_level=1,  # as a percent of the RMSE of the training data
    tol_iter=300,
):
    """
    Stitch all the training and testing trajectories together?
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

    # define data structure for records
    xdot_rmse_errors = {}
    xdot_coef_errors = {}
    predicted_coefficients = {}
    best_threshold_values = {}
    best_normalized_coef_errors = {}

    # initialize structures
    num_attractors = len(systems_list)
    for system in systems_list:
        xdot_rmse_errors[system] = list()
        xdot_coef_errors[system] = list()
        predicted_coefficients[system] = list()
        best_threshold_values[system] = list()
        best_normalized_coef_errors[system] = list()

    # iterate over all systems and noise levels
    if normalize_columns:
        dtol = 1e-2  # threshold values will be higher if feature library is normalized
    else:
        dtol = 1e-6

    max_iter = 100
    poly_library = ps.PolynomialLibrary(degree=4)
    models = []
    x_dot_tests = []
    x_dot_test_preds = []
    condition_numbers = np.zeros(num_attractors)

    for i, attractor_name in enumerate(systems_list):
        print(i, " / ", num_attractors, ", System = ", attractor_name)

        x_train = np.copy(all_sols_train[attractor_name])
        rmse = mean_squared_error(x_train[0], np.zeros(x_train[0].shape), squared=False)
        x_train_noisy = x_train + np.random.normal(
            0, rmse / 100.0 * error_level, x_train.shape
        )
        x_test = np.copy(all_sols_test[attractor_name])
        t_train = all_t_train[attractor_name]
        t_test = all_t_test[attractor_name]
        if dimension_list[i] == 3:
            input_names = ["x", "y", "z"]
        else:
            input_names = ["x", "y", "z", "w"]

        # feature_names = poly_library.fit(x_train).get_feature_names(input_names)

        # Sweep a Pareto front
        if coef_error_metric:
            (
                coef_best,
                err_best,
                coef_history,
                err_history,
                threshold_best,
                model,
                condition_numbers[i],
            ) = rudy_algorithm3(
                x_train_noisy,
                x_test,
                t_train,
                ode_lib=poly_library,
                dtol=dtol,
                optimizer_max_iter=max_iter,
                tol_iter=tol_iter,
                change_factor=1.1,
                l0_pen=l0_penalty,
                alpha=1e-5,
                normalize_columns=normalize_columns,
                t_test=t_test,
                input_names=input_names,
                coef_true=true_coefficients[i],
            )
        else:
            (
                coef_best,
                err_best,
                coef_history,
                err_history,
                threshold_best,
                model,
                condition_numbers[i],
            ) = rudy_algorithm2(
                x_train_noisy,
                x_test,
                t_train,
                ode_lib=poly_library,
                dtol=dtol,
                optimizer_max_iter=max_iter,
                tol_iter=tol_iter,
                change_factor=1.1,
                l0_pen=l0_penalty,
                alpha=1e-5,
                normalize_columns=normalize_columns,
                t_test=t_test,
                input_names=input_names,
            )

        x_dot_test = model.differentiate(x_test, t=t_test)
        x_dot_test_pred = model.predict(x_test)
        models.append(model)
        x_dot_tests.append(x_dot_test)
        x_dot_test_preds.append(x_dot_test_pred)
        best_threshold_values[attractor_name].append(threshold_best)
        xdot_rmse_errors[attractor_name].append(
            normalized_RMSE(x_dot_test, x_dot_test_pred)
        )
        xdot_coef_errors[attractor_name].append(
            coefficient_errors(true_coefficients[i], coef_best)
        )
        predicted_coefficients[attractor_name].append(coef_best)
        best_normalized_coef_errors[attractor_name].append(
            total_coefficient_error_normalized(true_coefficients[i], coef_best)
        )
    return (
        xdot_rmse_errors,
        xdot_coef_errors,
        x_dot_tests,
        x_dot_test_preds,
        predicted_coefficients,
        best_threshold_values,
        best_normalized_coef_errors,
        models,
        condition_numbers,
    )


def Pareto_scan_ensembling(
    systems_list,
    dimension_list,
    true_coefficients,
    all_sols_train,
    all_t_train,
    all_sols_test,
    all_t_test,
    l0_penalty=1e-5,
    normalize_columns=False,
    error_level=0,  # as a percent of the RMSE of the training data
    tol_iter=300,
    n_models=10,
    n_subset=40,
    replace=False,
    weak_form=False,
    algorithm="STLSQ",
):
    """
    Stitch all the training trajectories together and then subsample
    them to make n_models SINDy models. Pareto optimal is determined
    by computing the minimum average RMSE error in x_dot.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

    # define data structure for records
    xdot_rmse_errors = {}
    xdot_coef_errors = {}
    predicted_coefficients = {}
    best_threshold_values = {}
    best_normalized_coef_errors = {}

    # initialize structures
    num_attractors = len(systems_list)
    for system in systems_list:
        xdot_rmse_errors[system] = list()
        xdot_coef_errors[system] = list()
        predicted_coefficients[system] = list()
        best_threshold_values[system] = list()
        best_normalized_coef_errors[system] = list()

    # iterate over all systems and noise levels
    if normalize_columns:
        dtol = 1e-2  # threshold values will be higher if feature library is normalized
    else:
        dtol = 1e-6

    max_iter = 1000
    if not weak_form:
        poly_library = ps.PolynomialLibrary(degree=4)
    else:
        library_functions = [
            lambda x: x,
            lambda x: x * x,
            lambda x, y: x * y,
            lambda x: x * x * x,
            lambda x, y: x * x * y,
            lambda x, y: x * y * y,
            lambda x, y, z: x * y * z,
            lambda x: x * x * x * x,
            lambda x, y: x * x * x * y,
            lambda x, y: x * y * y * y,
            lambda x, y: x * x * y * y,
            lambda x, y, z: x * y * y * z,
            lambda x, y, z: x * y * z * z,
            lambda x, y, z: x * x * y * z,
            lambda x, y, z, w: x * y * z * w,
        ]
        library_function_names = [
            lambda x: x,
            lambda x: x + "^2",
            lambda x, y: x + " " + y,
            lambda x: x + "^3",
            lambda x, y: x + "^2 " + y,
            lambda x, y: x + " " + y + "^2",
            lambda x, y, z: x + " " + y + " " + z,
            lambda x: x + "^4",
            lambda x, y: x + "^3 " + y,
            lambda x, y: x + " " + y + "^3",
            lambda x, y: x + "^2 " + y + "^2",
            lambda x, y, z: x + " " + y + "^2 " + z,
            lambda x, y, z: x + " " + y + " " + z + "^2",
            lambda x, y, z: x + "^2 " + y + " " + z,
            lambda x, y, z, w: x + " " + y + " " + z + " " + w,
        ]
    models = []
    x_dot_tests = []
    x_dot_test_preds = []
    condition_numbers = np.zeros(num_attractors)
    t_start = time.time()

    for i, attractor_name in enumerate(systems_list):
        print(i, " / ", num_attractors, ", System = ", attractor_name)

        x_train = np.copy(all_sols_train[attractor_name])
        x_train_list = []
        t_train_list = []
        x_test_list = []
        t_test_list = []
        for j in range(len(x_train)):
            rmse = mean_squared_error(
                x_train[j], np.zeros(x_train[j].shape), squared=False
            )
            x_train_noisy = x_train[j] + np.random.normal(
                0, rmse / 100.0 * error_level, x_train[j].shape
            )
            x_train_list.append(x_train_noisy)
            x_test_list.append(all_sols_test[attractor_name][j])
            t_train_list.append(all_t_train[attractor_name][j])
            t_test_list.append(all_t_test[attractor_name][j])
        # x_test = all_sols_test[attractor_name]
        # t_test = all_t_test[attractor_name]
        if dimension_list[i] == 3:
            input_names = ["x", "y", "z"]
        else:
            input_names = ["x", "y", "z", "w"]

        # feature_names = poly_library.fit(x_train).get_feature_names(input_names)

        # Critical step for the weak form -- change the grid to match the system!
        if weak_form:
            poly_library = ps.WeakPDELibrary(
                library_functions=library_functions,
                function_names=library_function_names,
                spatiotemporal_grid=all_t_train[attractor_name][0],
                is_uniform=True,
                include_bias=True,
                K=100,
            )

        if algorithm == "MIOSR":
            # Sweep a Pareto front
            (
                coef_best,
                err_best,
                coef_history,
                err_history,
                threshold_best,
                model,
                condition_numbers[i],
            ) = rudy_algorithm_miosr(
                x_train_list,
                x_test_list,
                t_train_list,
                ode_lib=poly_library,
                l0_pen=l0_penalty,
                alpha=1e-5,
                normalize_columns=normalize_columns,
                t_test=t_test_list,
                input_names=input_names,
                ensemble=True,
                n_models=n_models,
                n_subset=n_subset,
                replace=replace,
            )
        elif algorithm == "SR3":
            # Sweep a Pareto front
            (
                coef_best,
                err_best,
                coef_history,
                err_history,
                threshold_best,
                model,
                condition_numbers[i],
            ) = rudy_algorithm_sr3(
                x_train_list,
                x_test_list,
                t_train_list,
                ode_lib=poly_library,
                dtol=dtol,
                optimizer_max_iter=max_iter,
                tol_iter=tol_iter,
                change_factor=1.1,
                l0_pen=l0_penalty,
                normalize_columns=normalize_columns,
                t_test=t_test_list,
                input_names=input_names,
                ensemble=True,
                n_models=n_models,
                n_subset=n_subset,
                replace=replace,
            )
        elif algorithm == "Lasso":
            # Sweep a Pareto front
            (
                coef_best,
                err_best,
                coef_history,
                err_history,
                threshold_best,
                model,
                condition_numbers[i],
            ) = rudy_algorithm_lasso(
                x_train_list,
                x_test_list,
                t_train_list,
                ode_lib=poly_library,
                dtol=dtol,
                optimizer_max_iter=max_iter,
                tol_iter=tol_iter,
                change_factor=1.1,
                l0_pen=l0_penalty,
                normalize_columns=normalize_columns,
                t_test=t_test_list,
                input_names=input_names,
                ensemble=True,
                n_models=n_models,
                n_subset=n_subset,
                replace=replace,
            )
        else:
            # Sweep a Pareto front
            (
                coef_best,
                err_best,
                coef_history,
                err_history,
                threshold_best,
                model,
                condition_numbers[i],
            ) = rudy_algorithm2(
                x_train_list,
                x_test_list,
                t_train_list,
                ode_lib=poly_library,
                dtol=dtol,
                optimizer_max_iter=max_iter,
                tol_iter=tol_iter,
                change_factor=1.1,
                l0_pen=l0_penalty,
                alpha=1e-5,
                normalize_columns=normalize_columns,
                t_test=t_test_list,
                input_names=input_names,
                ensemble=True,
                n_models=n_models,
                n_subset=n_subset,
                replace=replace,
            )

        print(model.get_feature_names())

        print(np.array(coef_best).shape, np.array(true_coefficients[i]).shape)
        x_dot_test = model.differentiate(
            x_test_list, t=t_test_list, multiple_trajectories=True
        )
        # print(model.optimizer.Theta_.shape, model.optimizer.coef_.shape, model.optimizer.coef_[0].shape, model.optimizer.coef_)
        # x_dot_test_pred = model.optimizer.Theta_ @ model.optimizer.coef_.T
        x_dot_test_pred = model.predict(x_test_list, multiple_trajectories=True)
        models.append(model)
        x_dot_tests.append(x_dot_test)
        x_dot_test_preds.append(x_dot_test_pred)
        best_threshold_values[attractor_name].append(threshold_best)
        xdot_rmse_errors[attractor_name].append(err_best)
        xdot_coef_errors[attractor_name].append(
            coefficient_errors(true_coefficients[i], np.mean(coef_best, axis=0))
        )
        predicted_coefficients[attractor_name].append(coef_best)
        best_normalized_coef_errors[attractor_name].append(
            total_coefficient_error_normalized(
                true_coefficients[i], np.mean(coef_best, axis=0)
            )
        )
    t_end = time.time()
    print("Total time = ", t_end - t_start)
    return (
        xdot_rmse_errors,
        xdot_coef_errors,
        x_dot_tests,
        x_dot_test_preds,
        predicted_coefficients,
        best_threshold_values,
        best_normalized_coef_errors,
        models,
        condition_numbers,
    )


def nonlinear_terms_from_coefficients(true_coefficients):
    # number of terms that are constant, linear, quadratic, cubic, and quartic
    num_attractors = len(true_coefficients)
    number_nonlinear_terms = np.zeros((num_attractors, 5))
    for i in range(num_attractors):
        dim = true_coefficients[i].shape[0]
        number_nonlinear_terms[i, 0] = np.count_nonzero(true_coefficients[i][:, 0])
        number_nonlinear_terms[i, 1] = np.count_nonzero(
            true_coefficients[i][:, 1 : dim + 1]
        )
        num_quad = int(comb(2 + dim - 1, dim - 1))
        num_cubic = int(comb(3 + dim - 1, dim - 1))
        num_quartic = int(comb(4 + dim - 1, dim - 1))
        coeff_index = dim + 1 + num_quad
        number_nonlinear_terms[i, 2] = np.count_nonzero(
            true_coefficients[i][:, dim + 1 : coeff_index]
        )
        number_nonlinear_terms[i, 3] = np.count_nonzero(
            true_coefficients[i][:, coeff_index : coeff_index + num_cubic]
        )
        coeff_index += num_cubic
        number_nonlinear_terms[i, 4] = np.count_nonzero(
            true_coefficients[i][:, coeff_index:]
        )
    return number_nonlinear_terms


def get_nonlinear_terms(num_attractors):
    # number of terms that are constant, linear, quadratic, cubic, and quartic
    number_nonlinear_terms = np.zeros((num_attractors + 1, 5))
    # Aizawa
    number_nonlinear_terms[0, 0] = 1
    number_nonlinear_terms[0, 1] = 5
    number_nonlinear_terms[0, 2] = 4
    number_nonlinear_terms[0, 3] = 3
    number_nonlinear_terms[0, 4] = 1
    # Arneodo
    number_nonlinear_terms[1, 1] = 5
    number_nonlinear_terms[1, 3] = 1
    # Bouali
    number_nonlinear_terms[2, 1] = 5
    number_nonlinear_terms[2, 2] = 2
    number_nonlinear_terms[2, 3] = 1
    # GenesioTesi
    number_nonlinear_terms[3, 1] = 5
    number_nonlinear_terms[3, 2] = 1
    # HyperBao
    number_nonlinear_terms[4, 1] = 6
    number_nonlinear_terms[4, 2] = 3
    # HyperCai
    number_nonlinear_terms[5, 1] = 7
    number_nonlinear_terms[5, 2] = 2
    # HyperJha
    number_nonlinear_terms[6, 1] = 7
    number_nonlinear_terms[6, 2] = 3
    # HyperLorenz
    number_nonlinear_terms[7, 1] = 7
    number_nonlinear_terms[7, 2] = 3
    # HyperLu
    number_nonlinear_terms[8, 1] = 6
    number_nonlinear_terms[8, 2] = 3
    # HyperPang
    number_nonlinear_terms[9, 1] = 7
    number_nonlinear_terms[9, 2] = 2
    # Laser
    number_nonlinear_terms[10, 1] = 4
    number_nonlinear_terms[10, 2] = 1
    number_nonlinear_terms[10, 3] = 2
    # Lorenz
    number_nonlinear_terms[11, 1] = 5
    number_nonlinear_terms[11, 2] = 2
    # LorenzBounded
    number_nonlinear_terms[12, 1] = 5
    number_nonlinear_terms[12, 2] = 2
    number_nonlinear_terms[12, 3] = 15
    number_nonlinear_terms[12, 4] = 6
    # MooreSpiegel
    number_nonlinear_terms[13, 1] = 5
    number_nonlinear_terms[13, 3] = 1
    # Rossler
    number_nonlinear_terms[14, 0] = 1
    number_nonlinear_terms[14, 1] = 5
    number_nonlinear_terms[14, 2] = 1
    # ShimizuMorioka
    number_nonlinear_terms[15, 1] = 4
    number_nonlinear_terms[15, 2] = 2
    # HenonHeiles
    number_nonlinear_terms[16, 1] = 4
    number_nonlinear_terms[16, 2] = 3
    # GuckenheimerHolmes
    number_nonlinear_terms[17, 0] = 1
    number_nonlinear_terms[17, 1] = 4
    number_nonlinear_terms[17, 2] = 5
    number_nonlinear_terms[17, 3] = 3
    # Halvorsen
    number_nonlinear_terms[18, 1] = 9
    number_nonlinear_terms[18, 2] = 3
    # KawczynskiStrizhak
    number_nonlinear_terms[19, 0] = 1
    number_nonlinear_terms[19, 1] = 7
    number_nonlinear_terms[19, 3] = 1
    # VallisElNino
    number_nonlinear_terms[20, 0] = 2
    number_nonlinear_terms[20, 1] = 4
    number_nonlinear_terms[20, 2] = 2
    # RabinovichFabrikant
    number_nonlinear_terms[21, 1] = 5
    number_nonlinear_terms[21, 2] = 2
    number_nonlinear_terms[21, 3] = 3
    # NoseHoover
    number_nonlinear_terms[22, 0] = 1
    number_nonlinear_terms[22, 1] = 2
    number_nonlinear_terms[22, 2] = 2
    # Dadras
    number_nonlinear_terms[23, 1] = 5
    number_nonlinear_terms[23, 2] = 3
    # RikitakeDynamo
    number_nonlinear_terms[24, 0] = 1
    number_nonlinear_terms[24, 1] = 3
    number_nonlinear_terms[24, 2] = 3
    # NuclearQuadrupole
    number_nonlinear_terms[25, 1] = 4
    number_nonlinear_terms[25, 2] = 3
    number_nonlinear_terms[25, 3] = 4
    # PehlivanWei
    number_nonlinear_terms[26, 0] = 1
    number_nonlinear_terms[26, 1] = 3
    number_nonlinear_terms[26, 2] = 4
    # SprottTorus
    number_nonlinear_terms[27, 0] = 1
    number_nonlinear_terms[27, 1] = 2
    number_nonlinear_terms[27, 2] = 6
    # SprottJerk
    number_nonlinear_terms[28, 1] = 4
    number_nonlinear_terms[28, 2] = 1
    # SprottA
    number_nonlinear_terms[29, 0] = 1
    number_nonlinear_terms[29, 1] = 2
    number_nonlinear_terms[29, 2] = 2
    # SprottB
    number_nonlinear_terms[30, 0] = 1
    number_nonlinear_terms[30, 1] = 3
    number_nonlinear_terms[30, 2] = 2
    # SprottC
    number_nonlinear_terms[31, 0] = 1
    number_nonlinear_terms[31, 1] = 2
    number_nonlinear_terms[31, 2] = 2
    # SprottD
    number_nonlinear_terms[32, 1] = 3
    number_nonlinear_terms[32, 2] = 2
    # SprottE
    number_nonlinear_terms[33, 0] = 1
    number_nonlinear_terms[33, 1] = 2
    number_nonlinear_terms[33, 2] = 2
    # SprottF
    number_nonlinear_terms[34, 1] = 5
    number_nonlinear_terms[34, 2] = 1
    # SprottG
    number_nonlinear_terms[35, 1] = 5
    number_nonlinear_terms[35, 2] = 1
    # SprottH
    number_nonlinear_terms[36, 1] = 5
    number_nonlinear_terms[36, 2] = 1
    # SprottI
    number_nonlinear_terms[37, 1] = 5
    number_nonlinear_terms[37, 2] = 1
    # SprottJ
    number_nonlinear_terms[38, 1] = 5
    number_nonlinear_terms[38, 2] = 1
    # SprottK
    number_nonlinear_terms[39, 1] = 5
    number_nonlinear_terms[39, 2] = 1
    # SprottL
    number_nonlinear_terms[40, 0] = 1
    number_nonlinear_terms[40, 1] = 4
    number_nonlinear_terms[40, 2] = 1
    # SprottM
    number_nonlinear_terms[41, 0] = 1
    number_nonlinear_terms[41, 1] = 4
    number_nonlinear_terms[41, 2] = 1
    # SprottN
    number_nonlinear_terms[42, 0] = 1
    number_nonlinear_terms[42, 1] = 4
    number_nonlinear_terms[42, 2] = 1
    # SprottO
    number_nonlinear_terms[43, 1] = 5
    number_nonlinear_terms[43, 2] = 1
    # SprottP
    number_nonlinear_terms[44, 1] = 5
    number_nonlinear_terms[44, 2] = 1
    # SprottQ
    number_nonlinear_terms[45, 1] = 5
    number_nonlinear_terms[45, 2] = 1
    # SprottR
    number_nonlinear_terms[46, 0] = 2
    number_nonlinear_terms[46, 1] = 3
    number_nonlinear_terms[46, 2] = 1
    # SprottS
    number_nonlinear_terms[47, 0] = 1
    number_nonlinear_terms[47, 1] = 4
    number_nonlinear_terms[47, 2] = 1
    # Rucklidge
    number_nonlinear_terms[48, 1] = 4
    number_nonlinear_terms[48, 2] = 2
    # Sakarya
    number_nonlinear_terms[49, 1] = 5
    number_nonlinear_terms[49, 2] = 3
    # RayleighBenard
    number_nonlinear_terms[50, 1] = 4
    number_nonlinear_terms[50, 2] = 2
    # Finance
    number_nonlinear_terms[51, 1] = 5
    number_nonlinear_terms[51, 2] = 2
    # LuChenCheng
    number_nonlinear_terms[52, 0] = 1
    number_nonlinear_terms[52, 1] = 3
    number_nonlinear_terms[52, 2] = 3
    # LuChen
    number_nonlinear_terms[53, 1] = 4
    number_nonlinear_terms[53, 2] = 2
    # QiChen
    number_nonlinear_terms[54, 1] = 5
    number_nonlinear_terms[54, 2] = 3
    # ZhouChen
    number_nonlinear_terms[55, 1] = 4
    number_nonlinear_terms[55, 2] = 4
    # BurkeShaw
    number_nonlinear_terms[56, 0] = 1
    number_nonlinear_terms[56, 1] = 3
    number_nonlinear_terms[56, 2] = 2
    # Chen
    number_nonlinear_terms[57, 1] = 5
    number_nonlinear_terms[57, 2] = 2
    # ChenLee
    number_nonlinear_terms[58, 1] = 3
    number_nonlinear_terms[58, 2] = 3
    # WangSun
    number_nonlinear_terms[59, 1] = 4
    number_nonlinear_terms[59, 2] = 3
    # DequanLi
    number_nonlinear_terms[60, 1] = 5
    number_nonlinear_terms[60, 2] = 4
    # NewtonLiepnik
    number_nonlinear_terms[61, 1] = 5
    number_nonlinear_terms[61, 2] = 3
    # HyperRossler
    number_nonlinear_terms[62, 0] = 1
    number_nonlinear_terms[62, 1] = 7
    number_nonlinear_terms[62, 2] = 1
    # HyperQi
    number_nonlinear_terms[63, 1] = 8
    number_nonlinear_terms[63, 2] = 4
    # Qi
    number_nonlinear_terms[64, 1] = 6
    number_nonlinear_terms[64, 3] = 4
    # LorenzStenflo
    number_nonlinear_terms[65, 1] = 8
    number_nonlinear_terms[65, 2] = 2
    # HyperYangChen
    number_nonlinear_terms[66, 1] = 6
    number_nonlinear_terms[66, 2] = 2
    # HyperYan
    number_nonlinear_terms[67, 1] = 7
    number_nonlinear_terms[67, 2] = 6
    # HyperXu
    number_nonlinear_terms[68, 1] = 6
    number_nonlinear_terms[68, 2] = 3
    # HyperWang
    number_nonlinear_terms[69, 1] = 6
    number_nonlinear_terms[69, 2] = 2
    # AtmosphericRegime
    number_nonlinear_terms[70, 1] = 5
    number_nonlinear_terms[70, 2] = 6
    # Hadley
    number_nonlinear_terms[71, 0] = 2
    number_nonlinear_terms[71, 1] = 3
    number_nonlinear_terms[71, 2] = 6
    # Hindmarsh
    number_nonlinear_terms[72, 0] = 1
    number_nonlinear_terms[72, 1] = 6
    number_nonlinear_terms[72, 2] = 2
    number_nonlinear_terms[72, 3] = 2
    return number_nonlinear_terms


def rudy_algorithm2(
    x_train,
    x_test,
    t_train,
    t_test,
    ode_lib,
    dtol,
    alpha=1e-5,
    tol_iter=25,
    change_factor=2,
    l0_pen=1e-3,
    normalize_columns=True,
    optimizer_max_iter=20,
    input_names=["x", "y", "z"],
    ensemble=False,
    n_models=10,
    n_subset=40,
    replace=False,
):
    """
    # Algorithm to scan over threshold values during Ridge Regression, and select
    # highest performing model on the test set
    """

    n_trajectories = np.array(x_test).shape[0]
    n_state = np.array(x_test).shape[2]
    if isinstance(ode_lib, ps.WeakPDELibrary):
        weak_form = True
        n_time = ode_lib.K
    else:
        weak_form = False
        n_time = np.array(x_test).shape[1]

    # Do an initial least-squares fit to get an initial guess of the coefficients
    # start with initial guess that all coefs are zero
    optimizer = ps.EnsembleOptimizer(
        opt=ps.STLSQ(
            threshold=0,
            alpha=alpha,
            max_iter=optimizer_max_iter,
            normalize_columns=normalize_columns,
            ridge_kw={"tol": 1e-10},
        ),
        bagging=ensemble,
        n_models=n_models,
        n_subset=n_subset,
        replace=replace,
        # ensemble_aggregator=np.mean
    )

    # Compute initial model
    model = ps.SINDy(
        feature_library=ode_lib, optimizer=optimizer, feature_names=input_names
    )
    model.fit(
        x_train,
        t=t_train,
        quiet=True,
        multiple_trajectories=True,
    )
    condition_number = np.linalg.cond(optimizer.Theta_)

    # Set the L0 penalty based on the condition number of Theta
    l0_penalty = l0_pen  # * np.linalg.cond(optimizer.Theta_)
    coef_best = np.array(optimizer.coef_list)
    optimizer.coef_ = np.mean(coef_best, axis=0)
    model_best = model

    # For each model, compute x_dot_test and compute the RMSE error
    error_new = np.zeros(n_models)
    error_best = np.zeros(n_models)

    for i in range(n_models):
        optimizer.coef_ = coef_best[i, :, :]
        x_dot_test = model.differentiate(x_test, t=t_test, multiple_trajectories=True)
        x_dot_test_pred = model.predict(x_test, multiple_trajectories=True)
        error_best[i] = normalized_RMSE(
            np.array(x_dot_test).reshape(n_trajectories * n_time, n_state),
            np.array(x_dot_test_pred).reshape(n_trajectories * n_time, n_state),
        ) + l0_penalty * np.count_nonzero(coef_best[i, :, :])

    coef_history_ = np.zeros(
        (n_models, coef_best.shape[1], coef_best.shape[2], 1 + tol_iter)
    )
    error_history_ = np.zeros((n_models, 1 + tol_iter))
    coef_history_[:, :, :, 0] = coef_best
    error_history_[:, 0] = error_best
    tol = dtol
    threshold_best = tol

    # Loop over threshold values, note needs some coding
    # if not using STLSQ optimizer
    for i in range(tol_iter):
        optimizer = ps.EnsembleOptimizer(
            opt=ps.STLSQ(
                threshold=tol,
                alpha=alpha,
                max_iter=optimizer_max_iter,
                normalize_columns=normalize_columns,
                ridge_kw={"tol": 1e-10},
            ),
            bagging=ensemble,
            n_models=n_models,
            n_subset=n_subset,
            replace=replace,
            # ensemble_aggregator=np.mean
        )
        model = ps.SINDy(
            feature_library=ode_lib, optimizer=optimizer, feature_names=input_names
        )
        model.fit(
            x_train,
            t=t_train,
            quiet=True,
            multiple_trajectories=True,
        )

        # For each model, compute x_dot_test and compute the RMSE error
        coef_new = np.array(optimizer.coef_list)
        if np.isclose(np.sum(coef_new), 0.0):
            break

        for j in range(n_models):
            optimizer.coef_ = np.copy(coef_new[j, :, :])
            model.optimizer.coef_ = np.copy(coef_new[j, :, :])
            x_dot_test = model.differentiate(
                x_test, t=t_test, multiple_trajectories=True
            )
            # x_dot_test_pred = model.predict(x_test, multiple_trajectories=True)
            x_dot_test_pred = model.predict(x_test, multiple_trajectories=True)
            # x_dot_test_pred = optimizer.Theta_ @ coef_new[j, :, :].T
            error_new[j] = normalized_RMSE(
                np.array(x_dot_test).reshape(n_trajectories * n_time, n_state),
                np.array(x_dot_test_pred).reshape(n_trajectories * n_time, n_state),
            ) + l0_penalty * np.count_nonzero(coef_new[j, :, :])
            # print(j, error_new[j], coef_new[j, :, :])
        # print(i, error_new)

        coef_history_[:, :, :, i + 1] = coef_new
        error_history_[:, i + 1] = error_new

        # If error improves, set the new best coefficients
        # Note < not <= since if all coefficients are zero,
        # this would still keep increasing the threshold!
        if np.mean(error_new) < np.mean(error_best):
            error_best = np.copy(error_new)
            coef_best = np.copy(coef_new)
            threshold_best = tol
            model.optimizer.coef_ = np.median(coef_new, axis=0)
            # model.optimizer.coef_ = model.optimizer.coef_[abs(model.optimizer.coef_) > 1e-2]
            model_best = model
        dtol = dtol * change_factor
        tol += dtol

    return (
        coef_best,
        error_best,
        coef_history_,
        error_history_,
        threshold_best,
        model_best,
        condition_number,
    )


def rudy_algorithm_lasso(
    x_train,
    x_test,
    t_train,
    t_test,
    ode_lib,
    dtol,
    alpha=1e-5,
    tol_iter=25,
    change_factor=2,
    l0_pen=1e-3,
    normalize_columns=True,
    optimizer_max_iter=20,
    input_names=["x", "y", "z"],
    ensemble=False,
    n_models=10,
    n_subset=40,
    replace=False,
):
    """
    # Algorithm to scan over threshold values during Ridge Regression, and select
    # highest performing model on the test set
    """

    n_trajectories = np.array(x_test).shape[0]
    n_state = np.array(x_test).shape[2]
    if isinstance(ode_lib, ps.WeakPDELibrary):
        weak_form = True
        n_time = ode_lib.K
    else:
        weak_form = False
        n_time = np.array(x_test).shape[1]

    # Do an initial least-squares fit to get an initial guess of the coefficients
    # start with initial guess that all coefs are zero
    optimizer = ps.EnsembleOptimizer(
        opt=Lasso(
            alpha=0, max_iter=optimizer_max_iter, fit_intercept=False
        ),  # currently ignoring normalize_columns parameter
        bagging=ensemble,
        n_models=n_models,
        n_subset=n_subset,
        replace=replace,
        # ensemble_aggregator=np.mean
    )

    # Compute initial model
    model = ps.SINDy(
        feature_library=ode_lib, optimizer=optimizer, feature_names=input_names
    )
    model.fit(
        x_train,
        t=t_train,
        quiet=True,
        multiple_trajectories=True,
    )
    condition_number = np.linalg.cond(optimizer.Theta_)

    # Set the L0 penalty based on the condition number of Theta
    l0_penalty = l0_pen  # * np.linalg.cond(optimizer.Theta_)
    coef_best = np.array(optimizer.coef_list)
    optimizer.coef_ = np.mean(coef_best, axis=0)
    model_best = model

    # For each model, compute x_dot_test and compute the RMSE error
    error_new = np.zeros(n_models)
    error_best = np.zeros(n_models)

    for i in range(n_models):
        optimizer.coef_ = coef_best[i, :, :]
        x_dot_test = model.differentiate(x_test, t=t_test, multiple_trajectories=True)
        x_dot_test_pred = model.predict(x_test, multiple_trajectories=True)
        error_best[i] = normalized_RMSE(
            np.array(x_dot_test).reshape(n_trajectories * n_time, n_state),
            np.array(x_dot_test_pred).reshape(n_trajectories * n_time, n_state),
        ) + l0_penalty * np.count_nonzero(coef_best[i, :, :])

    coef_history_ = np.zeros(
        (n_models, coef_best.shape[1], coef_best.shape[2], 1 + tol_iter)
    )
    error_history_ = np.zeros((n_models, 1 + tol_iter))
    coef_history_[:, :, :, 0] = coef_best
    error_history_[:, 0] = error_best
    tol = dtol
    threshold_best = tol

    # Loop over threshold values, note needs some coding
    # if not using STLSQ optimizer
    for i in range(tol_iter):
        optimizer = ps.EnsembleOptimizer(
            opt=Lasso(alpha=tol, max_iter=optimizer_max_iter, fit_intercept=False),
            bagging=ensemble,
            n_models=n_models,
            n_subset=n_subset,
            replace=replace,
            # ensemble_aggregator=np.mean
        )
        model = ps.SINDy(
            feature_library=ode_lib, optimizer=optimizer, feature_names=input_names
        )
        model.fit(
            x_train,
            t=t_train,
            quiet=True,
            multiple_trajectories=True,
        )

        # For each model, compute x_dot_test and compute the RMSE error
        coef_new = np.array(optimizer.coef_list)
        if np.isclose(np.sum(coef_new), 0.0):
            break

        for j in range(n_models):
            optimizer.coef_ = np.copy(coef_new[j, :, :])
            model.optimizer.coef_ = np.copy(coef_new[j, :, :])
            x_dot_test = model.differentiate(
                x_test, t=t_test, multiple_trajectories=True
            )
            # x_dot_test_pred = model.predict(x_test, multiple_trajectories=True)
            x_dot_test_pred = model.predict(x_test, multiple_trajectories=True)
            # x_dot_test_pred = optimizer.Theta_ @ coef_new[j, :, :].T
            error_new[j] = normalized_RMSE(
                np.array(x_dot_test).reshape(n_trajectories * n_time, n_state),
                np.array(x_dot_test_pred).reshape(n_trajectories * n_time, n_state),
            ) + l0_penalty * np.count_nonzero(coef_new[j, :, :])
            # print(j, error_new[j], coef_new[j, :, :])
        # print(i, error_new)

        coef_history_[:, :, :, i + 1] = coef_new
        error_history_[:, i + 1] = error_new

        # If error improves, set the new best coefficients
        # Note < not <= since if all coefficients are zero,
        # this would still keep increasing the threshold!
        if np.mean(error_new) < np.mean(error_best):
            error_best = np.copy(error_new)
            coef_best = np.copy(coef_new)
            threshold_best = tol
            model.optimizer.coef_ = np.median(coef_new, axis=0)
            # model.optimizer.coef_ = model.optimizer.coef_[abs(model.optimizer.coef_) > 1e-2]
            model_best = model
        dtol = dtol * change_factor
        tol += dtol

    return (
        coef_best,
        error_best,
        coef_history_,
        error_history_,
        threshold_best,
        model_best,
        condition_number,
    )


def rudy_algorithm_sr3(
    x_train,
    x_test,
    t_train,
    t_test,
    ode_lib,
    dtol,
    tol_iter=25,
    change_factor=2,
    l0_pen=1e-3,
    normalize_columns=True,
    optimizer_max_iter=20,
    input_names=["x", "y", "z"],
    ensemble=False,
    n_models=10,
    n_subset=40,
    replace=False,
):
    """
    # Algorithm to scan over threshold values during Ridge Regression, and select
    # highest performing model on the test set
    """

    n_trajectories = np.array(x_test).shape[0]
    n_state = np.array(x_test).shape[2]
    if isinstance(ode_lib, ps.WeakPDELibrary):
        weak_form = True
        n_time = ode_lib.K
    else:
        weak_form = False
        n_time = np.array(x_test).shape[1]

    # Do an initial least-squares fit to get an initial guess of the coefficients
    # start with initial guess that all coefs are zero
    optimizer = ps.EnsembleOptimizer(
        opt=ps.SR3(
            threshold=0,
            max_iter=optimizer_max_iter,
            normalize_columns=normalize_columns,
        ),
        bagging=ensemble,
        n_models=n_models,
        n_subset=n_subset,
        replace=replace,
        # ensemble_aggregator=np.mean
    )

    # Compute initial model
    model = ps.SINDy(
        feature_library=ode_lib, optimizer=optimizer, feature_names=input_names
    )
    model.fit(
        x_train,
        t=t_train,
        quiet=True,
        multiple_trajectories=True,
    )
    condition_number = np.linalg.cond(optimizer.Theta_)

    # Set the L0 penalty based on the condition number of Theta
    l0_penalty = l0_pen  # * np.linalg.cond(optimizer.Theta_)
    coef_best = np.array(optimizer.coef_list)
    optimizer.coef_ = np.mean(coef_best, axis=0)
    model_best = model

    # For each model, compute x_dot_test and compute the RMSE error
    error_new = np.zeros(n_models)
    error_best = np.zeros(n_models)

    for i in range(n_models):
        optimizer.coef_ = coef_best[i, :, :]
        x_dot_test = model.differentiate(x_test, t=t_test, multiple_trajectories=True)
        x_dot_test_pred = model.predict(x_test, multiple_trajectories=True)
        error_best[i] = normalized_RMSE(
            np.array(x_dot_test).reshape(n_trajectories * n_time, n_state),
            np.array(x_dot_test_pred).reshape(n_trajectories * n_time, n_state),
        ) + l0_penalty * np.count_nonzero(coef_best[i, :, :])

    coef_history_ = np.zeros(
        (n_models, coef_best.shape[1], coef_best.shape[2], 1 + tol_iter)
    )
    error_history_ = np.zeros((n_models, 1 + tol_iter))
    coef_history_[:, :, :, 0] = coef_best
    error_history_[:, 0] = error_best
    tol = dtol
    threshold_best = tol

    # Loop over threshold values, note needs some coding
    # if not using STLSQ optimizer
    for i in range(tol_iter):
        optimizer = ps.EnsembleOptimizer(
            opt=ps.SR3(
                threshold=tol,
                max_iter=optimizer_max_iter,
                normalize_columns=normalize_columns,
            ),
            bagging=ensemble,
            n_models=n_models,
            n_subset=n_subset,
            replace=replace,
            # ensemble_aggregator=np.mean
        )
        model = ps.SINDy(
            feature_library=ode_lib, optimizer=optimizer, feature_names=input_names
        )
        model.fit(
            x_train,
            t=t_train,
            quiet=True,
            multiple_trajectories=True,
        )

        # For each model, compute x_dot_test and compute the RMSE error
        coef_new = np.array(optimizer.coef_list)
        if np.isclose(np.sum(coef_new), 0.0):
            break

        for j in range(n_models):
            optimizer.coef_ = np.copy(coef_new[j, :, :])
            model.optimizer.coef_ = np.copy(coef_new[j, :, :])
            x_dot_test = model.differentiate(
                x_test, t=t_test, multiple_trajectories=True
            )
            # x_dot_test_pred = model.predict(x_test, multiple_trajectories=True)
            x_dot_test_pred = model.predict(x_test, multiple_trajectories=True)
            # x_dot_test_pred = optimizer.Theta_ @ coef_new[j, :, :].T
            error_new[j] = normalized_RMSE(
                np.array(x_dot_test).reshape(n_trajectories * n_time, n_state),
                np.array(x_dot_test_pred).reshape(n_trajectories * n_time, n_state),
            ) + l0_penalty * np.count_nonzero(coef_new[j, :, :])
            # print(j, error_new[j], coef_new[j, :, :])
        # print(i, error_new)

        coef_history_[:, :, :, i + 1] = coef_new
        error_history_[:, i + 1] = error_new

        # If error improves, set the new best coefficients
        # Note < not <= since if all coefficients are zero,
        # this would still keep increasing the threshold!
        if np.mean(error_new) < np.mean(error_best):
            error_best = np.copy(error_new)
            coef_best = np.copy(coef_new)
            threshold_best = tol
            model.optimizer.coef_ = np.median(coef_new, axis=0)
            # model.optimizer.coef_ = model.optimizer.coef_[abs(model.optimizer.coef_) > 1e-2]
            model_best = model
        dtol = dtol * change_factor
        tol += dtol

    return (
        coef_best,
        error_best,
        coef_history_,
        error_history_,
        threshold_best,
        model_best,
        condition_number,
    )


def rudy_algorithm_miosr(
    x_train,
    x_test,
    t_train,
    t_test,
    ode_lib,
    alpha=1e-5,
    l0_pen=1e-3,
    normalize_columns=True,
    input_names=["x", "y", "z"],
    ensemble=False,
    n_models=10,
    n_subset=40,
    replace=False,
):
    """
    # Algorithm to scan over threshold values during Ridge Regression, and select
    # highest performing model on the test set
    """

    n_trajectories = np.array(x_test).shape[0]
    n_state = np.array(x_test).shape[2]
    if isinstance(ode_lib, ps.WeakPDELibrary):
        weak_form = True
        n_time = ode_lib.K
    else:
        weak_form = False
        n_time = np.array(x_test).shape[1]

    # Do an initial least-squares fit to get an initial guess of the coefficients
    # start with initial guess that all coefs are zero
    optimizer = ps.EnsembleOptimizer(
        opt=ps.MIOSR(
            target_sparsity=1,
            alpha=alpha,
            normalize_columns=normalize_columns,
            regression_timeout=100,
        ),
        bagging=ensemble,
        n_models=n_models,
        n_subset=n_subset,
        replace=replace,
        # ensemble_aggregator=np.mean
    )

    # Compute initial model
    model = ps.SINDy(
        feature_library=ode_lib, optimizer=optimizer, feature_names=input_names
    )
    model.fit(
        x_train,
        t=t_train,
        quiet=True,
        multiple_trajectories=True,
    )
    condition_number = np.linalg.cond(optimizer.Theta_)
    print(np.shape(optimizer.Theta_))
    tol_iter = np.shape(optimizer.Theta_)[1] - 1

    # Set the L0 penalty based on the condition number of Theta
    l0_penalty = l0_pen  # * np.linalg.cond(optimizer.Theta_)
    coef_best = np.array(optimizer.coef_list)
    optimizer.coef_ = np.mean(coef_best, axis=0)
    model_best = model

    # For each model, compute x_dot_test and compute the RMSE error
    error_new = np.zeros(n_models)
    error_best = np.zeros(n_models)

    for i in range(n_models):
        optimizer.coef_ = coef_best[i, :, :]
        x_dot_test = model.differentiate(x_test, t=t_test, multiple_trajectories=True)
        x_dot_test_pred = model.predict(x_test, multiple_trajectories=True)
        error_best[i] = normalized_RMSE(
            np.array(x_dot_test).reshape(n_trajectories * n_time, n_state),
            np.array(x_dot_test_pred).reshape(n_trajectories * n_time, n_state),
        ) + l0_penalty * np.count_nonzero(coef_best[i, :, :])

    coef_history_ = np.zeros(
        (n_models, coef_best.shape[1], coef_best.shape[2], 1 + tol_iter)
    )
    error_history_ = np.zeros((n_models, 1 + tol_iter))
    coef_history_[:, :, :, 0] = coef_best
    error_history_[:, 0] = error_best
    sparsity_best = 0

    # Loop over threshold values, note needs some coding
    # if not using STLSQ optimizer
    for i in range(tol_iter):
        # print(i)
        optimizer = ps.EnsembleOptimizer(
            opt=ps.MIOSR(
                target_sparsity=i + 1,
                alpha=alpha,
                normalize_columns=normalize_columns,
                regression_timeout=0.5,
            ),
            bagging=ensemble,
            n_models=n_models,
            n_subset=n_subset,
            replace=replace,
            # ensemble_aggregator=np.mean
        )
        model = ps.SINDy(
            feature_library=ode_lib, optimizer=optimizer, feature_names=input_names
        )
        # t_start = time.time()
        model.fit(
            x_train,
            t=t_train,
            quiet=True,
            multiple_trajectories=True,
        )
        # t_end = time.time()
        # print(t_end - t_start)

        # For each model, compute x_dot_test and compute the RMSE error
        coef_new = np.array(optimizer.coef_list)
        if np.isclose(np.sum(coef_new), 0.0):
            break

        for j in range(n_models):
            optimizer.coef_ = np.copy(coef_new[j, :, :])
            model.optimizer.coef_ = np.copy(coef_new[j, :, :])
            x_dot_test = model.differentiate(
                x_test, t=t_test, multiple_trajectories=True
            )
            # x_dot_test_pred = model.predict(x_test, multiple_trajectories=True)
            x_dot_test_pred = model.predict(x_test, multiple_trajectories=True)
            # x_dot_test_pred = optimizer.Theta_ @ coef_new[j, :, :].T
            error_new[j] = normalized_RMSE(
                np.array(x_dot_test).reshape(n_trajectories * n_time, n_state),
                np.array(x_dot_test_pred).reshape(n_trajectories * n_time, n_state),
            ) + l0_penalty * np.count_nonzero(coef_new[j, :, :])
            # print(j, error_new[j], coef_new[j, :, :])
        # print(i, error_new)

        coef_history_[:, :, :, i + 1] = coef_new
        error_history_[:, i + 1] = error_new

        # If error improves, set the new best coefficients
        # Note < not <= since if all coefficients are zero,
        # this would still keep increasing the threshold!
        if np.mean(error_new) < np.mean(error_best):
            error_best = np.copy(error_new)
            coef_best = np.copy(coef_new)
            sparsity_best = i
            model.optimizer.coef_ = np.median(coef_new, axis=0)
            # model.optimizer.coef_ = model.optimizer.coef_[abs(model.optimizer.coef_) > 1e-2]
            model_best = model

    return (
        coef_best,
        error_best,
        coef_history_,
        error_history_,
        sparsity_best,
        model_best,
        condition_number,
    )


def rudy_algorithm3(
    x_train,
    x_test,
    t_train,
    t_test,
    ode_lib,
    dtol,
    coef_true,
    alpha=1e-5,
    tol_iter=25,
    change_factor=2,
    l0_pen=1e-3,
    normalize_columns=True,
    optimizer_max_iter=20,
    input_names=["x", "y", "z"],
):
    """
    Algorithm to scan over threshold values during Ridge Regression, and select
    highest performing model on the test set using the coefficient error!
    """

    # Do an initial least-squares fit to get an initial guess of the coefficients
    # start with initial guess that all coefs are zero
    optimizer = ps.STLSQ(
        threshold=0,
        alpha=alpha,
        max_iter=optimizer_max_iter,
        normalize_columns=normalize_columns,
        ridge_kw={"tol": 1e-10},
    )

    # Compute initial model
    model = ps.SINDy(
        feature_library=ode_lib, optimizer=optimizer, feature_names=input_names
    )
    model.fit(x_train, t=t_train, quiet=True)
    model_best = model
    condition_number = np.linalg.cond(optimizer.Theta_)

    # Set the L0 penalty based on the condition number of Theta
    l0_penalty = l0_pen  # * np.linalg.cond(optimizer.Theta_)
    coef_best = optimizer.coef_

    error_best = total_coefficient_error_normalized(
        coef_true, coef_best
    ) + l0_penalty * np.count_nonzero(coef_best)

    coef_history_ = np.zeros((coef_best.shape[0], coef_best.shape[1], 1 + tol_iter))
    error_history_ = np.zeros(1 + tol_iter)
    coef_history_[:, :, 0] = coef_best
    error_history_[0] = error_best
    tol = dtol
    threshold_best = tol

    # Loop over threshold values, note needs some coding
    # if not using STLSQ optimizer
    for i in range(tol_iter):
        optimizer = ps.STLSQ(
            threshold=tol,
            alpha=alpha,
            max_iter=optimizer_max_iter,
            normalize_columns=normalize_columns,
            ridge_kw={"tol": 1e-10},
        )
        model = ps.SINDy(
            feature_library=ode_lib, optimizer=optimizer, feature_names=input_names
        )
        model.fit(x_train, t=t_train, quiet=True)
        coef_new = optimizer.coef_
        if np.isclose(np.sum(coef_new), 0.0):
            break
        coef_history_[:, :, i + 1] = coef_new
        error_new = total_coefficient_error_normalized(
            coef_true, coef_new
        ) + l0_penalty * np.count_nonzero(coef_new)
        error_history_[i + 1] = error_new

        # If error improves, set the new best coefficients
        # Note < not <= since if all coefficients are zero,
        # this would still keep increasing the threshold!
        if error_new < error_best:
            error_best = error_new
            coef_best = coef_new
            threshold_best = tol
            model_best = model
        dtol = dtol * change_factor
        tol += dtol

    return (
        coef_best,
        error_best,
        coef_history_,
        error_history_,
        threshold_best,
        model_best,
        condition_number,
    )


def rudy_algorithm4(
    x_train,
    x_test,
    t_train,
    t_test,
    ode_lib,
    dtol,
    coef_true,
    alpha=1e-5,
    tol_iter=25,
    change_factor=2,
    l0_pen=1e-3,
    normalize_columns=True,
    optimizer_max_iter=20,
    input_names=["x", "y", "z"],
):
    """
    Algorithm to scan over threshold values during Ridge Regression, and select
    highest performing model on the test set using the coefficient error
    on the testing trajectory, not is derivative!
    """

    # Do an initial least-squares fit to get an initial guess of the coefficients
    # start with initial guess that all coefs are zero
    optimizer = ps.STLSQ(
        threshold=0,
        alpha=alpha,
        max_iter=optimizer_max_iter,
        normalize_columns=normalize_columns,
        ridge_kw={"tol": 1e-10},
    )

    # Compute initial model
    model = ps.SINDy(
        feature_library=ode_lib, optimizer=optimizer, feature_names=input_names
    )
    model.fit(x_train, t=t_train, quiet=True)
    model_best = model
    condition_number = np.linalg.cond(optimizer.Theta_)
    x_pred = model.simulate(x_test[0, :], t_test)

    # Set the L0 penalty based on the condition number of Theta
    l0_penalty = l0_pen  # * np.linalg.cond(optimizer.Theta_)
    coef_best = optimizer.coef_

    error_best = normalized_RMSE(x_test, x_pred) + l0_penalty * np.count_nonzero(
        coef_best
    )

    coef_history_ = np.zeros((coef_best.shape[0], coef_best.shape[1], 1 + tol_iter))
    error_history_ = np.zeros(1 + tol_iter)
    coef_history_[:, :, 0] = coef_best
    error_history_[0] = error_best
    tol = dtol
    threshold_best = tol

    # Loop over threshold values, note needs some coding
    # if not using STLSQ optimizer
    for i in range(tol_iter):
        optimizer = ps.STLSQ(
            threshold=tol,
            alpha=alpha,
            max_iter=optimizer_max_iter,
            normalize_columns=normalize_columns,
            ridge_kw={"tol": 1e-10},
        )
        model = ps.SINDy(
            feature_library=ode_lib, optimizer=optimizer, feature_names=input_names
        )
        model.fit(x_train, t=t_train, quiet=True)
        coef_new = optimizer.coef_
        if np.isclose(np.sum(coef_new), 0.0):
            break
        coef_history_[:, :, i + 1] = coef_new
        # x_dot_test = model.differentiate(x_test, t=t_test)
        # x_dot_test_pred = model.predict(x_test)
        traj_errors = np.zeros(num_trajectories)
        num_bounded = num_trajectories
        for j in range(num_trajectories):
            x_pred = model.simulate(test_trajectories[0, j, :], t=t_test)
            traj_errors[j] = normalized_RMSE(
                test_trajectories[:, j, :], x_pred
            ) + l0_penalty * np.count_nonzero(coef_new)
            if traj_errors[j] > 1e2:
                num_bounded -= 1
        error_new = np.mean(traj_errors)
        error_history_[i + 1] = error_new

        # If error improves, set the new best coefficients
        # Note < not <= since if all coefficients are zero,
        # this would still keep increasing the threshold!
        if error_new < error_best:
            error_best = error_new
            coef_best = coef_new
            threshold_best = tol
            model_best = model
        dtol = dtol * change_factor
        tol += dtol

    return (
        coef_best,
        error_best,
        coef_history_,
        error_history_,
        threshold_best,
        model_best,
        condition_number,
    )


def make_dysts_true_coefficients(
    systems_list, all_sols_train, dimension_list, param_list
):
    """
    Turn python functions into strings that we can use to extract the coefficients!
    """
    poly_library = ps.PolynomialLibrary(degree=4)
    true_coefficients = []

    for i, system in enumerate(systems_list):
        # print(i, system)
        x_train = all_sols_train[system][0]
        if dimension_list[i] == 3:
            feature_names = poly_library.fit(x_train).get_feature_names(["x", "y", "z"])
        else:
            feature_names = poly_library.fit(x_train).get_feature_names(
                ["x", "y", "z", "w"]
            )
        for k, feature in enumerate(feature_names):
            feature = feature.replace(" ", "", 10)
            feature = feature.replace("y^3z", "zy^3", 10)
            feature = feature.replace("x^3z", "zx^3", 10)
            feature = feature.replace("x^3y", "yx^3", 10)
            feature = feature.replace("z^3y", "yz^3", 10)
            feature = feature.replace("y^3x", "xy^3", 10)
            feature = feature.replace("z^3x", "xz^3", 10)
            feature_names[k] = feature
        # print(feature_names)
        num_poly = len(feature_names)
        coef_matrix_i = np.zeros((dimension_list[i], num_poly))
        system_str = inspect.getsource(getattr(flows, system))
        cut1 = system_str.find("return")
        system_str = system_str[: cut1 - 1]
        cut2 = system_str.rfind("):")
        system_str = system_str[cut2 + 5 :]
        chunks = system_str.split("\n")[:-1]
        params = param_list[i]
        # print(system, chunks)
        for j, chunk in enumerate(chunks):
            cind = chunk.rfind("=")
            chunk = chunk[cind + 1 :]
            for key in params.keys():
                if "Lorenz" in system and "rho" in params.keys():
                    chunk = chunk.replace("rho", str(params["rho"]), 10)
                if "Bouali2" in system:
                    chunk = chunk.replace("bb", "0", 10)
                chunk = chunk.replace(key, str(params[key]), 10)
            # print(chunk)
            chunk = chunk.replace("--", "", 10)
            chunk = chunk.replace("- -", "+ ", 10)
            # get all variables into (x, y, z, w) form
            chunk = chunk.replace("q1", "x", 10)
            chunk = chunk.replace("q2", "y", 10)
            chunk = chunk.replace("p1", "z", 10)
            chunk = chunk.replace("p2", "w", 10)
            chunk = chunk.replace("px", "z", 10)
            chunk = chunk.replace("py", "w", 10)
            # change notation of squared and cubed terms
            chunk = chunk.replace(" ** 2", "^2", 10)
            chunk = chunk.replace(" ** 3", "^3", 10)
            # reorder cubic terms
            chunk = chunk.replace("y * x^2", "x^2y", 10)
            chunk = chunk.replace("z * x^2", "x^2z", 10)
            chunk = chunk.replace("z * y^2", "y^2z", 10)
            # reorder quartic terms
            chunk = chunk.replace("y * x^3", "yx^3", 10)
            chunk = chunk.replace("z * x^3", "zx^3", 10)
            chunk = chunk.replace("z * y^2", "zy^3", 10)
            # Reorder quadratics
            chunk = chunk.replace("x * y", "xy", 10)
            chunk = chunk.replace("x * z", "xz", 10)
            chunk = chunk.replace("y * x", "xy", 10)
            chunk = chunk.replace("z * x", "xz", 10)
            chunk = chunk.replace("y * z", "yz", 10)
            chunk = chunk.replace("z * y", "yz", 10)
            chunk = chunk.replace("x * w", "xw", 10)
            chunk = chunk.replace("w * x", "xw", 10)
            chunk = chunk.replace("y * w", "yw", 10)
            chunk = chunk.replace("w * y", "yw", 10)
            chunk = chunk.replace("z * w", "zw", 10)
            chunk = chunk.replace("w * z", "zw", 10)

            # Do any unique ones
            chunk = chunk.replace("1 / 0.03", "33.3333333333", 10)
            chunk = chunk.replace("1.0 / 0.03", "33.3333333333", 10)
            chunk = chunk.replace("1 / 0.8", "1.25", 10)
            chunk = chunk.replace("1.0 / 0.8", "1.25", 10)
            chunk = chunk.replace("0.0322 / 0.8", "0.04025", 10)
            chunk = chunk.replace("0.49 / 0.03", "16.3333333333", 10)
            chunk = chunk.replace("(-10 + -4)", "-14", 10)
            chunk = chunk.replace("(-10 * -4)", "40", 10)
            chunk = chunk.replace("3.0 * 1.0", "3", 10)
            chunk = chunk.replace(" - 0 * z", "", 10)
            chunk = chunk.replace("(28 - 35)", "-7", 10)
            chunk = chunk.replace("(1 / 0.2 - 0.001)", "4.999", 10)
            chunk = chunk.replace("- (1.0 - 1.0) * x^2 ", "", 10)
            chunk = chunk.replace("(26 - 37)", "-11", 10)
            chunk = chunk.replace("64^2", "4096", 10)
            chunk = chunk.replace("64**2", "4096", 10)
            chunk = chunk.replace("3 / np.sqrt(2) * 0.55", "1.166726189", 10)
            chunk = chunk.replace("3 * np.sqrt(2) * 0.55", "2.333452378", 10)
            chunk = chunk.replace("+ -", "- ", 10)
            chunk = chunk.replace("-1.5 * -0.0026667", "0.00400005", 10)

            for num_str in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]:
                for x_str in ["x", "y", "z", "w"]:
                    chunk = chunk.replace(num_str + " * " + x_str, num_str + x_str, 20)

            chunk = chunk.replace("- 0.0026667 * 0xz", "", 10)
            chunk = chunk.replace("1/4096", "0.000244140625", 10)
            chunk = chunk.replace("10/4096", "0.00244140625", 10)
            chunk = chunk.replace("28/4096", "0.0068359375", 10)
            chunk = chunk.replace("2.667/4096", "0.000651123046875", 10)
            chunk = chunk.replace("0.2 * 9", "1.8", 10)
            chunk = chunk.replace(" - 3 * 0", "", 10)
            chunk = chunk.replace("2 * 1", "2", 10)
            chunk = chunk.replace("3 * 2.1 * 0.49", "3.087", 10)
            chunk = chunk.replace("2 * 2.1", "4.2", 10)
            chunk = chunk.replace("-40 / -14", "2.85714285714", 10)
            # change notation of squared and cubed terms
            chunk = chunk.replace(" 1x", " x", 10)
            chunk = chunk.replace(" 1y", " y", 10)
            chunk = chunk.replace(" 1z", " z", 10)
            chunk = chunk.replace(" 1w", " w", 10)
            chunks[j] = chunk
            chunk = chunk.replace(" ", "", 400)
            chunk = chunk.replace("-x", "-1x", 10)
            chunk = chunk.replace("-y", "-1y", 10)
            chunk = chunk.replace("-z", "-1z", 10)
            chunk = chunk.replace("-w", "-1w", 10)
            chunk = chunk.replace("--", "-", 20)
            #         chunk = chunk.replace('- x', '-1x')
            #         chunkt = feature_chunk_compact.replace('- y', '-1y')
            #         chunk = feature_chunk_compact.replace('- z', '-1z')
            #         chunk = feature_chunk_compact.replace('- w', '-1w')

            # Okay strings are formatted. Time to read them into the
            # coefficient matrix
            for k, feature in enumerate(np.flip(feature_names[1:])):
                # print(k, feature)
                feature_ind = (chunk + " ").find(feature)
                if feature_ind != -1:
                    feature_chunk = chunk[: feature_ind + len(feature)]
                    find = max(feature_chunk.rfind("+"), feature_chunk.rfind("-"))
                    # print('find = ', find, feature_chunk)
                    if find == -1 or find == 0:
                        feature_chunk = feature_chunk[0:] + " "
                    else:
                        feature_chunk = feature_chunk[find:] + " "
                    # print(feature_chunk)
                    if feature_chunk != chunk:
                        feature_chunk_compact = feature_chunk.replace("+", "")
                        # print(feature, feature_chunk_compact[:-len(feature) - 1])
                        if (
                            len(
                                feature_chunk_compact[: -len(feature) - 1].replace(
                                    " ", ""
                                )
                            )
                            == 0
                        ):
                            coef_matrix_i[j, len(feature_names) - k - 1] = 1
                        else:
                            coef_matrix_i[j, len(feature_names) - k - 1] = float(
                                feature_chunk_compact[: -len(feature) - 1]
                            )
                        # print(feature_chunk, chunk)
                        chunk = chunk.replace(feature_chunk.replace(" ", ""), "")
                        #
                        # print(feature, 'Chunk after = ', chunk)
                        # if len(chunk.replace(' ', '')) == 0:
                        #    break
            if len(chunk.replace(" ", "")) != 0:
                coef_matrix_i[j, 0] = chunk.replace(" ", "")

        true_coefficients.append(coef_matrix_i)
    return true_coefficients