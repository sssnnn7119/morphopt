import morphopt

if __name__ == "__main__":
    morphopt.start_optimization(path_result='Z:/Results/RIGID_T20260109_164123/',
                                  target_iteration=None,
                                  device='cuda',
                                  restart_per_iteration=20,)