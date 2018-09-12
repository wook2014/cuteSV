import cigar
import gc
# INS_flag = {1:'I'}
# DEL_flag = {2:'D'}

candidate = dict()

def detect_flag(Flag):
	# Signal
	Normal_foward = 1 >> 1
	Abnormal = 1 << 2
	Reverse_complement = 1 << 4
	Supplementary_map = 1 << 11

	signal = {Abnormal: 0, Normal_foward: 1, Reverse_complement: 2, Supplementary_map:3, Reverse_complement | Supplementary_map:4}
	if Flag in signal:
		return signal[Flag]
	else:
		return 0

def search_indel_str(deal_cigar, pos_start, SV_size, Chr_name, RLength):
	seq = list(cigar.Cigar(deal_cigar).items())
	Ins_list = list()
	Del_list = list()
	shift_ins = 0
	shift_del = 0
	for element in seq:
		if element[1] == 'M' or element[1] == 'D':
			shift_ins += element[0]
		if element[1] == 'I' and element[0] > SV_size:
			shift_ins += 1
			Ins_list.append([Chr_name, pos_start + shift_ins, element[0]])

		if element[1] == 'M':
			shift_del += element[0]
		if element[1] == 'D' and element[0] < SV_size:
			shift_del += element[0]
		if element[1] == 'D' and element[0] >= SV_size:
			Del_list.append([Chr_name, pos_start + shift_del, element[0]])
			shift_del += element[0]

	if seq[0][1] == 'S':
		softclip_left = seq[0][0]
	else:
		softclip_left = 0
	if seq[-1][1] == 'S':
		softclip_right = seq[-1][0]
	else:
		softclip_right = 0
	clip_list = [softclip_left, RLength - softclip_right, pos_start, pos_start + shift_ins, Chr_name]

	return Ins_list, Del_list, clip_list

def search_indel_list(deal_cigar, pos_start, SV_size, Chr_name, RLength):
	Ins_list = list()
	Del_list = list()
	shift_ins = 0
	shift_del = 0
	# _shift_read_ = 0
	for element in deal_cigar:
		if element[0] == 0 or element[0] == 2:
			shift_ins += element[1]
		# if element[0] != 2:
		# 	_shift_read_ += element[1]
		if element[0] == 1 and element[1] > SV_size:
			shift_ins += 1
			Ins_list.append([Chr_name, pos_start + shift_ins, element[1]])
			
		if element[0] == 0:
			shift_del += element[1]
		if element[0] == 2 and element[1] < SV_size:
			shift_del += element[1]
		if element[0] == 2 and element[1] >= SV_size:
			Del_list.append([Chr_name, pos_start + shift_del, element[1]])
			shift_del += element[1]

	if deal_cigar[0][0] == 4:
		softclip_left = deal_cigar[0][1]
	else:
		softclip_left = 0
	if deal_cigar[-1][0] == 4:
		softclip_right = deal_cigar[-1][1]
	else:
		softclip_right = 0

	clip_list = [softclip_left, RLength - softclip_right, pos_start + 1, pos_start + shift_ins + 1, Chr_name]
	return Ins_list, Del_list, clip_list

def analysis_split_read(split_read, SV_size, RLength):
	candidate_SV = dict()
	# +indel++indel++indel++indel++indel++indel+
	candidate_SV["Indel_Ins"] = list()
	candidate_SV["Indel_Del"] = list()
	SP_list = list()

	for read in split_read:
		if isinstance(read[3], str):
			Ins_list, Del_list, sp_list = search_indel_str(read[3], read[1], SV_size, read[0], RLength)
		else:
			Ins_list, Del_list, sp_list = search_indel_list(read[3], read[1], SV_size, read[0], RLength)
		candidate_SV["Indel_Del"] += Del_list
		candidate_SV["Indel_Ins"] += Ins_list
		sp_list += read[2]
		SP_list.append(sp_list)
	'''
	for i in candidate_SV["Indel_Ins"]:
		print "INS", i
	for i in candidate_SV["Indel_Del"]:
		print "DEL", i
	'''
	# split alignment
	SP_list = sorted(SP_list, key = lambda x:x[0])
	for i in SP_list:
	 	print i

	candidate_SV["DUP"] = list()
	# candidate_SV["INVDUP"] = list()
	candidate_SV["INS"] = list()
	candidate_SV["INV"] = list()
	candidate_SV["TRA"] = list()
	DUP_flag = [0]*len(SP_list)
	INVDUP_flag = [0]*len(SP_list)
	# INS_flag = [0]*len(SP_list)

	for a in SP_list:
		for b in SP_list:
			if a[4] == b[4]:
				# dup & INV & TRA & INS
				if b[3] - a[2] >= SV_size and SP_list.index(a) > SP_list.index(b):
					# dup
					# if a[5] == b[5]:
					# 	DUP_flag[SP_list.index(a)] = 1
					# 	DUP_flag[SP_list.index(b)] = 1
					# else:
					# 	INVDUP_flag[SP_list.index(a)] = 1
					# 	INVDUP_flag[SP_list.index(b)] = 1
					DUP_flag[SP_list.index(a)] = 1
					DUP_flag[SP_list.index(b)] = 1

				if a[0] + b[3] - a[2] - b[1] >= SV_size and b[3] <= a[2] and SP_list.index(a) == SP_list.index(b) + 1:
					candidate_SV["INS"].append([a[4], (a[2]+b[3])/2, a[0]+b[3]-a[2]-b[1]])

				# if b[1] <= a[0] and b[3] <= a[2] and b[5] != a[5] and SP_list.index(a) == SP_list.index(b) + 1:
				# 	if SP_list.index(a) + 2 <= len(SP_list):
				# 		# print SP_list[SP_list.index(a)+1]
				# 		if a[1] <= SP_list[SP_list.index(a)+1][0] and a[3] <= SP_list[SP_list.index(a)+1][2] and a[5] != SP_list[SP_list.index(a)+1][5]:
				# 			candidate_SV["INV"].append([a[4], (a[2]+b[3])/2, (SP_list[SP_list.index(a)+1][2]+b[3]-a[2]-a[3])/2])

			else:
				# tra
				if SP_list.index(a) > SP_list.index(b):
					if b[4] < a[4]:
						candidate_SV["TRA"].append([b[4], b[3], a[4], a[2]])
					else:
						candidate_SV["TRA"].append([a[4], a[2], b[4], b[3]])
	# for k in xrange(len(SP_list[:-1])):
	# 	for l in xrange(len(SP_list[1:])):
	# 		if SP_list[k][4] == SP_list[l][4] and SP_list[k][2] < SP_list[l][3]:
	# 			# chr & ovlapping cmp
	# 			if SP_list[k][5] == SP_list[l][5]:
	# 				DUP_flag[k] = 1
	# 				DUP_flag[l] = 1
	# 			else:
	# 				INVDUP_flag[k] = 1
	# 				INVDUP_flag[l] = 1

			# if SP_list[k+1][2] < SP_list[k][2]:
			# 	# overlap cmp
			# 	if SP_list[k+1][5] == SP_list[k][5]:
			# 		# strand cmp
			# 		if k == len(SP_list)-2:
			# 			local_candidate_DUP.append([SP_list[k][4], SP_list[k+1][2], -1])
			# 		else:
			# 			local_candidate_DUP.append([SP_list[k][4], SP_list[k+1][2], SP_list[k+1][3]])
					
			# 		if k == 0:
			# 			local_candidate_DUP.append([SP_list[k][4], -1, SP_list[k][3]])
			# 	else:
			# 		if k == len(SP_list)-2:
			# 			local_candidate_INVDUP.append([SP_list[k][4], SP_list[k+1][2], -1])
			# 		else:
			# 			local_candidate_INVDUP.append([SP_list[k][4], SP_list[k+1][2], SP_list[k+1][3]])
			# 		if k == 0:
			# 			local_candidate_INVDUP.append([SP_list[k][4], -1, SP_list[k][3]])

	# +DUP++DUP++DUP++DUP++DUP++DUP++DUP++DUP+
	# temp_dup_s = dict()
	# temp_invdup_s = dict()
	# temp_dup_e = dict()
	# temp_invdup_e = dict()
	for k in xrange(len(SP_list)):
		if DUP_flag[k] == 1:
			# if SP_list[k][4] not in temp_dup_e:
			# 	temp_dup_e[SP_list[k][4]] = list()
			# if SP_list[k][4] not in temp_dup_s:
			# 	temp_dup_s[SP_list[k][4]] = list()
			if k == 0:
				candidate_SV["DUP"].append([SP_list[k][4], -1, SP_list[k][3]])
				# temp_dup_e.append(SP_list[k][3])
				# temp_dup_e[SP_list[k][4]].append(SP_list[k][3])
			elif k == len(SP_list)-1:
				candidate_SV["DUP"].append([SP_list[k][4], SP_list[k][2], -1])
				# temp_dup_s.append(SP_list[k][2])
				# temp_dup_s[SP_list[k][4]].append(SP_list[k][2])
			else:
				candidate_SV["DUP"].append([SP_list[k][4], SP_list[k][2], SP_list[k][3]])
				# temp_dup_s.append(SP_list[k][2])
				# temp_dup_s[SP_list[k][4]].append(SP_list[k][2])
				# temp_dup_e.append(SP_list[k][3])
				# temp_dup_e[SP_list[k][4]].append(SP_list[k][3])
		if INVDUP_flag[k] == 1:
			# if SP_list[k][4] not in temp_invdup_e:
			# 	temp_invdup_e[SP_list[k][4]] = list()
			# if SP_list[k][4] not in temp_invdup_s:
			# 	temp_invdup_s[SP_list[k][4]] = list()
			if k == 0:
				candidate_SV["INVDUP"].append([SP_list[k][4], -1, SP_list[k][3]])
				# temp_invdup_e.append(SP_list[k][3])
				# temp_invdup_e[SP_list[k][4]].append(SP_list[k][3])
			elif k == len(SP_list)-1:
				candidate_SV["INVDUP"].append([SP_list[k][4], SP_list[k][2], -1])
				# temp_invdup_s.append(SP_list[k][2])
				# temp_invdup_s[SP_list[k][4]].append(SP_list[k][2])
			else:
				candidate_SV["INVDUP"].append([SP_list[k][4], SP_list[k][2], SP_list[k][3]])
				# temp_invdup_s.append(SP_list[k][2])
				# temp_invdup_s[SP_list[k][4]].append(SP_list[k][2])
				# temp_invdup_e.append(SP_list[k][3])
				# temp_invdup_e[SP_list[k][4]].append(SP_list[k][3])

	# for key in temp_dup_s:
	# 	candidate_SV["DUP"].append([key, int(sum(temp_dup_s[key])/len(temp_dup_s[key])), int(sum(temp_dup_e[key])/len(temp_dup_e[key])), max(len(temp_dup_e[key]), len(temp_dup_s[key]))])
	# for key in temp_invdup_s:
	# 	candidate_SV["INVDUP"].append([key, int(sum(temp_invdup_s[key])/len(temp_invdup_s[key])), int(sum(temp_invdup_e[key])/len(temp_invdup_e[key])), max(len(temp_invdup_e[key]), len(temp_invdup_s[key]))])
	# +TRA++TRA++TRA++TRA++TRA++TRA++TRA++TRA+

	# +INV++INV++INV++INV++INV++INV++INV++INV+
	temp_inv_s = dict()
	temp_inv_e = dict()
	call_inv = sorted(SP_list, key = lambda x:x[2])
	if len(call_inv) >= 3:
		for a in call_inv[:-2]:
			if a[5] != call_inv[call_inv.index(a)+1][5] and a[5] == call_inv[call_inv.index(a)+2][5] and a[4] == call_inv[call_inv.index(a)+1][4] and a[4] == call_inv[call_inv.index(a)+2][4]:
				if call_inv[call_inv.index(a)+1][3] - call_inv[call_inv.index(a)+1][2] >= SV_size:
					candidate_SV["INV"].append([a[4], a[3] , call_inv[call_inv.index(a)+1][3]])
					# if a[4] not in temp_inv_s:
					# 	temp_inv_s[a[4]] = list()
					# if a[4] not in temp_inv_e:
					# 	temp_inv_e[a[4]] = list()
					# temp_inv_s[a[4]].append(a[3])
					# temp_inv_e[a[4]].append(call_inv[call_inv.index(a)+1][3])

	if len(call_inv) == 2:
		# if call_inv[0][4] not in temp_inv_s:
		# 	temp_inv_s[call_inv[0][4]] = list()
		# if call_inv[0][4] not in temp_inv_e:
		# 	temp_inv_e[call_inv[0][4]] = list()
		if call_inv[0][5] != call_inv[1][5] and call_inv[0][4] == call_inv[1][4]:
			ls_1 = call_inv[0][3] - call_inv[0][2]
			ls_2 = call_inv[1][3] - call_inv[1][2]
			if ls_1 > ls_2:
				if call_inv[1][2] > call_inv[0][3] and ls_2 >= SV_size:
					# temp_inv_e[call_inv[0][4]].append(call_inv[1][3])
					candidate_SV["INV"].append([call_inv[0][4], -1 , call_inv[1][3]])
			else:
				if call_inv[1][2] > call_inv[0][3] and ls_1 >= SV_size:
					# temp_inv_s[call_inv[0][4]].append(call_inv[0][2])
					candidate_SV["INV"].append([call_inv[0][4], call_inv[0][2], -1])

	# for key in temp_inv_s:
	# 	try:
	# 		candidate_SV["INV"].append([key, int(sum(temp_inv_s[key])/len(temp_inv_s[key])), int(sum(temp_inv_e[key])/len(temp_inv_e[key]))])
	# 	except:
	# 		# pass
	# 		if len(temp_inv_s[key]) == 0 :
	# 			candidate_SV["INV"].append([key, -1, int(sum(temp_inv_e[key])/len(temp_inv_e[key]))])
	# 		if len(temp_inv_e[key]) == 0:
	# 			candidate_SV["INV"].append([key, int(sum(temp_inv_s[key])/len(temp_inv_s[key])), -1])

	print candidate_SV["DUP"]
	return candidate_SV

def parse_read(read, Chr_name, SV_size, MQ_threshold):
	process_signal = detect_flag(read.flag)
	if process_signal == 0:
		# unmapped reads
		# return INS_ME_pos
		pass
	# split alignment phasing
	if process_signal == 1 or process_signal == 2:
		split_read = list()
		if read.mapq > MQ_threshold:
			if read.is_reverse:
				strand = '-'
			else:
				strand = '+'
			split_read.append([Chr_name, read.reference_start, strand, read.cigar])
		Tags = read.get_tags()
		for tag in Tags:
			if tag[0] == 'SA':
				split_alignment = tag[1].split(';')[:-1]
				for mapping in split_alignment:
					parse_mapping = mapping.split(',')
					if int(parse_mapping[4]) < MQ_threshold:
						continue
					split_read.append([parse_mapping[0], int(parse_mapping[1]), parse_mapping[2], parse_mapping[3]])
				break

		print read.query_name
		# for key in split_read:
			# print isinstance(key[3], str), key[3]
		data = analysis_split_read(split_read, SV_size, read.query_length)
		gc.collect()

		for key in data:
			if key not in candidate:
				candidate[key] = list()
			for i in data[key]:
				candidate[key].append(i)
				# print key, i


def show_temp_result():
	for key in candidate:
		candidate[key] = sorted(candidate[key], key = lambda x:x[0:3])
		for i in candidate[key]:
			print key, i
